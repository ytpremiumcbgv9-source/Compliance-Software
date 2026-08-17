"""ComplyEase FastAPI server.

A PCS compliance workspace: approval-based auth, multi-client workspaces,
compliance register with audit trail, master data (directors / auditors /
financials), and a real Excel importer that maps source sheets into
those modules.
"""

import io
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import bcrypt
import jwt
import pandas as pd
from dotenv import load_dotenv
from fastapi import (APIRouter, Depends, FastAPI, File, HTTPException, Request,
                     Response, UploadFile)
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = mongo[os.environ["DB_NAME"]]

app = FastAPI(title="ComplyEase API")
api = APIRouter(prefix="/api")

JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = 8

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class SignupIn(BaseModel):
    name: str
    email: str
    password: str
    practice_name: str


class LoginIn(BaseModel):
    email: str
    password: str


class ApprovalIn(BaseModel):
    approved: bool
    client_limit: int = 5


class LimitIn(BaseModel):
    client_limit: int


class StatusIn(BaseModel):
    status: str  # approved | suspended


class ClientIn(BaseModel):
    name: str
    code: str
    cin: Optional[str] = None
    sector: str = "Private company"
    state: str = "Maharashtra"
    registered_address: Optional[str] = None
    incorporation_date: Optional[str] = None


class ClientPatch(BaseModel):
    name: Optional[str] = None
    cin: Optional[str] = None
    sector: Optional[str] = None
    state: Optional[str] = None
    registered_address: Optional[str] = None
    incorporation_date: Optional[str] = None


class ObligationUpdate(BaseModel):
    status: Optional[str] = None
    filed_date: Optional[str] = None
    srn: Optional[str] = None
    assignee: Optional[str] = None
    remarks: Optional[str] = None
    due: Optional[str] = None
    priority: Optional[str] = None


class DirectorIn(BaseModel):
    name: str
    din: Optional[str] = None
    designation: str = "Director"
    appointment_date: Optional[str] = None
    cessation_date: Optional[str] = None
    kyc_status: str = "Pending"
    email: Optional[str] = None
    pan: Optional[str] = None


class AuditorIn(BaseModel):
    firm_name: str
    frn: Optional[str] = None
    appointment_date: Optional[str] = None
    term_end_date: Optional[str] = None
    email: Optional[str] = None
    pan: Optional[str] = None


class FinancialsIn(BaseModel):
    fy_end: str
    revenue: Optional[float] = 0
    profit: Optional[float] = 0
    net_worth: Optional[float] = 0
    paid_up_capital: Optional[float] = 0
    borrowings: Optional[float] = 0
    turnover: Optional[float] = 0
    listed: bool = False


class ShareholderIn(BaseModel):
    name: str
    folio_no: Optional[str] = None
    pan: Optional[str] = None
    shares_held: Optional[float] = 0
    share_class: str = "Equity"
    date_of_holding: Optional[str] = None
    email: Optional[str] = None


class ChargeIn(BaseModel):
    charge_id: Optional[str] = None
    creation_date: Optional[str] = None
    amount: Optional[float] = 0
    holder: str
    description: Optional[str] = None
    status: str = "Open"
    modification_date: Optional[str] = None
    satisfaction_date: Optional[str] = None


class ResolutionIn(BaseModel):
    number: str
    passed_on: Optional[str] = None
    resolution_type: str = "Board"  # Board | Special | Ordinary | Circular
    subject: str
    body: Optional[str] = None
    filing_form: Optional[str] = None


class ContractIn(BaseModel):
    counterparty: str
    relationship: str = "Related party"
    nature: Optional[str] = None
    value: Optional[float] = 0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    approval_reference: Optional[str] = None


class GenerateFyIn(BaseModel):
    fy: str  # e.g. "2026-27"
    incorporation_only: bool = False


class SubmitIn(BaseModel):
    remarks: Optional[str] = None


class ReviewIn(BaseModel):
    approved: bool
    remarks: Optional[str] = None


class ImportApplyRow(BaseModel):
    """One target record + the sheet row it came from."""
    values: Dict[str, Any]


class ImportApply(BaseModel):
    client_id: str
    target: str  # directors | auditors | financials
    rows: List[Dict[str, Any]]


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------
def _fy_end_year(fy: str) -> int:
    """'2026-27' -> 2027"""
    parts = fy.split("-")
    return int("20" + parts[1]) if len(parts[1]) == 2 else int(parts[1])


def _fy_start_year(fy: str) -> int:
    return int(fy.split("-")[0])


def _iso(y: int, m: int, d: int) -> str:
    return f"{y:04d}-{m:02d}-{d:02d}"


# Compliance rule library — the recurring engine.
# offset semantics: "fy_end+Nd" => (fy_end + N days); "fixed:m-d" => that date in FY end year;
# "half1:m-d" / "half2:m-d" => two occurrences per FY on the given dates.
COMPLIANCE_RULES = [
    {"code": "MGT-7", "name": "Annual return", "form": "MGT-7", "section": "92",
     "category": "Annual filing", "priority": "High", "recurrence": "annual",
     "due_rule": "fy_end+60d",
     "description": "Annual return with directors, shareholders and other prescribed particulars."},
    {"code": "AOC-4", "name": "Financial statements", "form": "AOC-4", "section": "137",
     "category": "Annual filing", "priority": "Critical", "recurrence": "annual",
     "due_rule": "fy_end+30d_after_agm",
     "description": "File adopted financial statements with the Registrar within 30 days of AGM."},
    {"code": "DIR-3-KYC", "name": "Director KYC", "form": "DIR-3 KYC", "section": "153",
     "category": "Directors", "priority": "Critical", "recurrence": "annual",
     "due_rule": "fixed:09-30",
     "description": "Complete annual KYC for every active director holding a DIN as on 31 March."},
    {"code": "ADT-1", "name": "Auditor appointment", "form": "ADT-1", "section": "139",
     "category": "Audit", "priority": "High", "recurrence": "annual",
     "due_rule": "fy_end+15d",
     "description": "Intimation of appointment / reappointment of statutory auditor."},
    {"code": "DPT-3", "name": "Return of deposits", "form": "DPT-3", "section": "73",
     "category": "Deposits", "priority": "Medium", "recurrence": "annual",
     "due_rule": "half1:06-30",
     "description": "Return of deposits and outstanding money not treated as deposits."},
    {"code": "MSME-1-H1", "name": "MSME outstanding return (Apr–Sep)", "form": "MSME-1",
     "section": "405", "category": "MSME", "priority": "Medium", "recurrence": "half-yearly",
     "due_rule": "half1:10-31",
     "description": "Half-yearly return of MSME outstanding beyond 45 days (Apr–Sep window)."},
    {"code": "MSME-1-H2", "name": "MSME outstanding return (Oct–Mar)", "form": "MSME-1",
     "section": "405", "category": "MSME", "priority": "Medium", "recurrence": "half-yearly",
     "due_rule": "half2:04-30",
     "description": "Half-yearly return of MSME outstanding beyond 45 days (Oct–Mar window)."},
    {"code": "AGM", "name": "Hold Annual General Meeting", "form": "AGM", "section": "96",
     "category": "Governance", "priority": "Critical", "recurrence": "annual",
     "due_rule": "fixed:09-30",
     "description": "AGM to be held on or before 30 September of the following FY."},
    {"code": "BM-Q1", "name": "Board meeting — Q1", "form": "BM", "section": "173",
     "category": "Governance", "priority": "Medium", "recurrence": "quarterly",
     "due_rule": "quarter:1:06-30",
     "description": "Board meeting for the first quarter of the FY."},
    {"code": "BM-Q2", "name": "Board meeting — Q2", "form": "BM", "section": "173",
     "category": "Governance", "priority": "Medium", "recurrence": "quarterly",
     "due_rule": "quarter:2:09-30",
     "description": "Board meeting for the second quarter of the FY."},
    {"code": "BM-Q3", "name": "Board meeting — Q3", "form": "BM", "section": "173",
     "category": "Governance", "priority": "Medium", "recurrence": "quarterly",
     "due_rule": "quarter:3:12-31",
     "description": "Board meeting for the third quarter of the FY."},
    {"code": "BM-Q4", "name": "Board meeting — Q4", "form": "BM", "section": "173",
     "category": "Governance", "priority": "Medium", "recurrence": "quarterly",
     "due_rule": "quarter:4:03-31",
     "description": "Board meeting for the fourth quarter of the FY."},
    {"code": "CSR-2", "name": "CSR report", "form": "CSR-2", "section": "135",
     "category": "CSR", "priority": "Medium", "recurrence": "annual",
     "due_rule": "fy_end+90d",
     "description": "CSR reporting for eligible companies, filed as an addendum to AOC-4."},
    {"code": "MBP-1", "name": "Directors' disclosure of interest", "form": "MBP-1",
     "section": "184", "category": "Directors", "priority": "High", "recurrence": "annual",
     "due_rule": "quarter:1:04-30",
     "description": "Disclosure of interest by every director at the first board meeting of the FY."},
    {"code": "IEPF-2", "name": "Unclaimed dividend statement", "form": "IEPF-2",
     "section": "125", "category": "IEPF", "priority": "Medium", "recurrence": "annual",
     "due_rule": "fixed:09-30",
     "description": "Statement of unclaimed and unpaid amounts within 60 days of the AGM."},
]


def resolve_due(fy: str, rule: dict) -> str:
    end_y = _fy_end_year(fy)
    start_y = _fy_start_year(fy)
    fy_end = datetime(end_y, 3, 31)
    dr = rule["due_rule"]
    if dr.startswith("fy_end+"):
        n = int("".join(ch for ch in dr.split("+")[1] if ch.isdigit()))
        due = fy_end + timedelta(days=n)
        return due.strftime("%Y-%m-%d")
    if dr.startswith("fixed:"):
        m, d = dr.split(":")[1].split("-")
        return _iso(end_y, int(m), int(d))
    if dr.startswith("half1:"):
        m, d = dr.split(":")[1].split("-")
        return _iso(start_y, int(m), int(d))
    if dr.startswith("half2:"):
        m, d = dr.split(":")[1].split("-")
        return _iso(end_y, int(m), int(d))
    if dr.startswith("quarter:"):
        _, q, md = dr.split(":")
        m, d = md.split("-")
        year = start_y if int(m) >= 4 else end_y
        return _iso(year, int(m), int(d))
    return fy_end.strftime("%Y-%m-%d")

TARGET_FIELDS = {
    "directors": ["name", "din", "designation", "appointment_date", "cessation_date",
                  "kyc_status", "email", "pan"],
    "auditors": ["firm_name", "frn", "appointment_date", "term_end_date", "email", "pan"],
    "financials": ["fy_end", "revenue", "profit", "net_worth", "paid_up_capital",
                   "borrowings", "turnover", "listed"],
}

FIELD_SYNONYMS = {
    # directors
    "name": ["name", "director", "director name", "full name", "person"],
    "din": ["din", "dpin", "director identification"],
    "designation": ["designation", "role", "position"],
    "appointment_date": ["appointment", "appointed on", "date of appointment", "appointment date", "doa"],
    "cessation_date": ["cessation", "resignation", "date of cessation", "resigned on"],
    "kyc_status": ["kyc", "kyc status", "dir-3", "dir3 status"],
    "email": ["email", "e-mail", "email id"],
    "pan": ["pan", "pan no", "permanent account"],
    # auditors
    "firm_name": ["firm", "audit firm", "auditor", "firm name", "auditor name"],
    "frn": ["frn", "firm registration", "firm reg no"],
    "term_end_date": ["term end", "term ends", "term expiry", "end date"],
    # financials
    "fy_end": ["fy", "fy end", "year end", "financial year", "as at", "as on"],
    "revenue": ["revenue", "turnover from operations", "total income", "income"],
    "profit": ["profit", "pat", "net profit", "profit after tax"],
    "net_worth": ["net worth", "networth"],
    "paid_up_capital": ["paid up", "paid-up capital", "share capital"],
    "borrowings": ["borrowings", "loans", "debt"],
    "turnover": ["turnover", "sales"],
    "listed": ["listed", "listed status"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def make_token(user: dict) -> str:
    payload = {
        "sub": user["id"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_TTL_HOURS),
    }
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)


def public_user(user: dict) -> dict:
    keys = ("id", "name", "email", "practice_name", "role", "status", "client_limit")
    return {k: user[k] for k in keys if k in user}


def strip(doc: dict) -> dict:
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def current_user(request: Request) -> dict:
    raw = request.cookies.get("access_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not raw:
        raise HTTPException(401, "Please log in")
    try:
        payload = jwt.decode(raw, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Session expired")
    user = await db.users.find_one({"id": payload["sub"]}, {"_id": 0})
    if not user or user.get("status") != "approved":
        raise HTTPException(403, "Your account is awaiting owner approval")
    return user


async def owner_only(user: dict = Depends(current_user)) -> dict:
    if user.get("role") != "owner":
        raise HTTPException(403, "Owner access required")
    return user


async def ensure_owned_client(client_id: str, user: dict) -> dict:
    client = await db.clients.find_one({"id": client_id, "owner_user_id": user["id"]}, {"_id": 0})
    if not client:
        raise HTTPException(404, "Client not found")
    return client


async def log_audit(client_id: str, actor: dict, action: str, detail: str,
                    entity: str = "", entity_id: str = "") -> None:
    entry = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "actor_id": actor["id"],
        "actor_name": actor.get("name", ""),
        "action": action,
        "detail": detail,
        "entity": entity,
        "entity_id": entity_id,
        "created_at": now_iso(),
    }
    await db.audit_log.insert_one(dict(entry))


def guess_mapping(columns: List[str], target: str) -> Dict[str, str]:
    """Auto-suggest column → target field mapping using synonym match."""
    fields = TARGET_FIELDS.get(target, [])
    lowered = {c: c.strip().lower() for c in columns}
    mapping: Dict[str, str] = {}
    for field in fields:
        needles = FIELD_SYNONYMS.get(field, [field.replace("_", " ")])
        for col, low in lowered.items():
            if any(n in low for n in needles):
                mapping[field] = col
                break
    return mapping


def coerce(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value).strip() if not isinstance(value, (int, float, bool)) else value


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------
@api.get("/")
async def root():
    return {"message": "ComplyEase API ready"}


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
@api.post("/auth/signup")
async def signup(payload: SignupIn):
    email = payload.email.strip().lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(409, "An account with this email already exists")
    has_owner = await db.users.find_one({"role": "owner"})
    user = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "email": email,
        "practice_name": payload.practice_name,
        "password_hash": hash_password(payload.password),
        "role": "member" if has_owner else "owner",
        "status": "approved" if not has_owner else "pending",
        "client_limit": 5,
        "created_at": now_iso(),
    }
    await db.users.insert_one(dict(user))
    return {
        "message": "Owner account created" if not has_owner else "Request submitted for owner approval",
        "user": public_user(user),
    }


@api.post("/auth/login")
async def login(payload: LoginIn, response: Response):
    user = await db.users.find_one({"email": payload.email.strip().lower()}, {"_id": 0})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    if user.get("status") == "suspended":
        raise HTTPException(403, "Your account has been suspended by the owner")
    if user.get("status") != "approved":
        raise HTTPException(403, "Your signup request is awaiting owner approval")
    response.set_cookie(
        "access_token", make_token(user),
        httponly=True, secure=True, samesite="none",
        max_age=JWT_TTL_HOURS * 3600, path="/",
    )
    return public_user(user)


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/")
    return {"message": "Logged out"}


@api.get("/auth/me")
async def me(user=Depends(current_user)):
    return public_user(user)


# ---------------------------------------------------------------------------
# Owner administration
# ---------------------------------------------------------------------------
@api.get("/owner/requests")
async def list_requests(user=Depends(owner_only)):
    rows = await db.users.find({"status": "pending"}, {"_id": 0, "password_hash": 0}).to_list(200)
    return rows


@api.patch("/owner/requests/{user_id}")
async def approve_request(user_id: str, payload: ApprovalIn, user=Depends(owner_only)):
    status = "approved" if payload.approved else "rejected"
    result = await db.users.update_one(
        {"id": user_id, "status": "pending"},
        {"$set": {"status": status, "client_limit": max(1, payload.client_limit)}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Pending request not found")
    return {"message": f"Account {status}"}


@api.get("/owner/users")
async def list_users(user=Depends(owner_only)):
    users = await db.users.find(
        {"role": {"$ne": "owner"}}, {"_id": 0, "password_hash": 0}
    ).to_list(500)
    for u in users:
        u["clients_used"] = await db.clients.count_documents({"owner_user_id": u["id"]})
    return users


@api.patch("/owner/users/{user_id}/limit")
async def update_limit(user_id: str, payload: LimitIn, user=Depends(owner_only)):
    result = await db.users.update_one(
        {"id": user_id}, {"$set": {"client_limit": max(1, payload.client_limit)}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"message": "Client limit updated"}


@api.patch("/owner/users/{user_id}/status")
async def update_status(user_id: str, payload: StatusIn, user=Depends(owner_only)):
    if payload.status not in ("approved", "suspended"):
        raise HTTPException(400, "Status must be approved or suspended")
    result = await db.users.update_one({"id": user_id}, {"$set": {"status": payload.status}})
    if result.matched_count == 0:
        raise HTTPException(404, "User not found")
    return {"message": f"User {payload.status}"}


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------
@api.get("/clients")
async def list_clients(user=Depends(current_user)):
    rows = await db.clients.find({"owner_user_id": user["id"]}, {"_id": 0}).to_list(200)
    for row in rows:
        row["obligations_count"] = await db.obligations.count_documents({"client_id": row["id"]})
        row["overdue_count"] = await db.obligations.count_documents(
            {"client_id": row["id"], "status": "Overdue"}
        )
    return rows


@api.post("/clients")
async def create_client(payload: ClientIn, user=Depends(current_user)):
    count = await db.clients.count_documents({"owner_user_id": user["id"]})
    limit = int(user.get("client_limit", 5))
    if count >= limit:
        raise HTTPException(403, f"Your plan allows {limit} clients. Ask the owner to raise the limit.")
    item = {
        "id": str(uuid.uuid4()),
        "owner_user_id": user["id"],
        "health": 82,
        "created_at": now_iso(),
        **payload.model_dump(),
    }
    await db.clients.insert_one(dict(item))
    await log_audit(item["id"], user, "client.created", f"Created client workspace {payload.name}", "client", item["id"])
    return strip(item)


@api.patch("/clients/{client_id}")
async def update_client(client_id: str, payload: ClientPatch, user=Depends(current_user)):
    await ensure_owned_client(client_id, user)
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    if changes:
        await db.clients.update_one({"id": client_id}, {"$set": changes})
        await log_audit(client_id, user, "client.updated",
                        "Updated: " + ", ".join(changes.keys()), "client", client_id)
    return strip(await db.clients.find_one({"id": client_id}, {"_id": 0}))


@api.delete("/clients/{client_id}")
async def delete_client(client_id: str, user=Depends(current_user)):
    await ensure_owned_client(client_id, user)
    await db.clients.delete_one({"id": client_id})
    for col in ("obligations", "directors", "auditors", "financials", "evidence", "audit_log"):
        await db[col].delete_many({"client_id": client_id})
    return {"message": "Client removed"}


# ---------------------------------------------------------------------------
# Obligations
# ---------------------------------------------------------------------------
@api.get("/clients/{client_id}/obligations")
async def get_obligations(client_id: str, user=Depends(current_user)):
    await ensure_owned_client(client_id, user)
    rows = await db.obligations.find({"client_id": client_id}, {"_id": 0}).to_list(500)
    return rows


@api.patch("/obligations/{obligation_id}")
async def update_obligation(obligation_id: str, payload: ObligationUpdate, user=Depends(current_user)):
    row = await db.obligations.find_one({"id": obligation_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Obligation not found")
    await ensure_owned_client(row["client_id"], user)
    changes = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not changes:
        return row
    await db.obligations.update_one({"id": obligation_id}, {"$set": changes})
    await log_audit(row["client_id"], user, "obligation.updated",
                    f"{row['form']} · " + ", ".join(f"{k}={v}" for k, v in changes.items()),
                    "obligation", obligation_id)
    return strip(await db.obligations.find_one({"id": obligation_id}, {"_id": 0}))


# ---------------------------------------------------------------------------
# Master data — directors, auditors, financials
# ---------------------------------------------------------------------------
def _master_router(collection: str, model, entity_label: str):
    async def _list(client_id: str, user=Depends(current_user)):
        await ensure_owned_client(client_id, user)
        return await db[collection].find({"client_id": client_id}, {"_id": 0}).to_list(500)

    async def _create(client_id: str, payload: model, user=Depends(current_user)):
        await ensure_owned_client(client_id, user)
        item = {"id": str(uuid.uuid4()), "client_id": client_id,
                "created_at": now_iso(), **payload.model_dump()}
        await db[collection].insert_one(dict(item))
        await log_audit(client_id, user, f"{entity_label}.added",
                        f"Added {entity_label}", entity_label, item["id"])
        return strip(item)

    async def _delete(client_id: str, item_id: str, user=Depends(current_user)):
        await ensure_owned_client(client_id, user)
        result = await db[collection].delete_one({"id": item_id, "client_id": client_id})
        if result.deleted_count:
            await log_audit(client_id, user, f"{entity_label}.removed",
                            f"Removed {entity_label}", entity_label, item_id)
        return {"message": "Removed"}

    return _list, _create, _delete


list_directors, add_director, remove_director = _master_router("directors", DirectorIn, "director")
list_auditors, add_auditor, remove_auditor = _master_router("auditors", AuditorIn, "auditor")
list_financials, add_financials, remove_financials = _master_router("financials", FinancialsIn, "financials")

api.add_api_route("/clients/{client_id}/directors", list_directors, methods=["GET"])
api.add_api_route("/clients/{client_id}/directors", add_director, methods=["POST"])
api.add_api_route("/clients/{client_id}/directors/{item_id}", remove_director, methods=["DELETE"])
api.add_api_route("/clients/{client_id}/auditors", list_auditors, methods=["GET"])
api.add_api_route("/clients/{client_id}/auditors", add_auditor, methods=["POST"])
api.add_api_route("/clients/{client_id}/auditors/{item_id}", remove_auditor, methods=["DELETE"])
api.add_api_route("/clients/{client_id}/financials", list_financials, methods=["GET"])
api.add_api_route("/clients/{client_id}/financials", add_financials, methods=["POST"])
api.add_api_route("/clients/{client_id}/financials/{item_id}", remove_financials, methods=["DELETE"])


# ---------------------------------------------------------------------------
# Audit log + evidence
# ---------------------------------------------------------------------------
@api.get("/clients/{client_id}/audit-log")
async def get_audit_log(client_id: str, user=Depends(current_user)):
    await ensure_owned_client(client_id, user)
    rows = await db.audit_log.find({"client_id": client_id}, {"_id": 0}) \
        .sort("created_at", -1).to_list(300)
    return rows


@api.get("/clients/{client_id}/evidence")
async def list_evidence(client_id: str, user=Depends(current_user)):
    await ensure_owned_client(client_id, user)
    return await db.evidence.find({"client_id": client_id}, {"_id": 0}).to_list(500)


@api.post("/clients/{client_id}/evidence")
async def upload_evidence(client_id: str, file: UploadFile = File(...), user=Depends(current_user)):
    await ensure_owned_client(client_id, user)
    record = {
        "id": str(uuid.uuid4()),
        "client_id": client_id,
        "filename": file.filename,
        "content_type": file.content_type,
        "uploaded_at": now_iso(),
        "uploaded_by": user["name"],
    }
    await db.evidence.insert_one(dict(record))
    await log_audit(client_id, user, "evidence.uploaded",
                    f"Uploaded evidence {file.filename}", "evidence", record["id"])
    return strip(record)


# ---------------------------------------------------------------------------
# Imports — preview + apply
# ---------------------------------------------------------------------------
@api.post("/imports/preview")
async def import_preview(file: UploadFile = File(...), user=Depends(current_user)):
    content = await file.read()
    try:
        book = pd.ExcelFile(io.BytesIO(content))
    except Exception:
        raise HTTPException(400, "Please upload a valid Excel workbook (.xlsx)")

    sheets = []
    for sheet in book.sheet_names:
        try:
            frame = pd.read_excel(io.BytesIO(content), sheet_name=sheet).fillna("")
        except Exception:
            continue
        columns = [str(c) for c in frame.columns]
        sample = frame.head(5).astype(str).to_dict("records")
        rows = frame.to_dict("records")
        # coerce timestamps/NaN to JSON-safe values
        rows = [{str(k): coerce(v) for k, v in row.items()} for row in rows]
        low = sheet.lower()
        if any(k in low for k in ("director", "kmp", "board")):
            suggestion = "directors"
        elif any(k in low for k in ("auditor", "adt")):
            suggestion = "auditors"
        elif any(k in low for k in ("financial", "p&l", "balance", "revenue", "profit", "figures")):
            suggestion = "financials"
        else:
            suggestion = "directors"
        sheets.append({
            "name": sheet,
            "columns": columns,
            "sample": sample,
            "rows_count": len(rows),
            "rows": rows,
            "suggested_target": suggestion,
            "suggested_mapping": guess_mapping(columns, suggestion),
        })

    return {
        "filename": file.filename,
        "sheets": sheets,
        "targets": {t: TARGET_FIELDS[t] for t in TARGET_FIELDS},
        "message": "Workbook scanned. Review the suggested mapping for each sheet before importing.",
    }


@api.post("/imports/apply")
async def import_apply(payload: ImportApply, user=Depends(current_user)):
    await ensure_owned_client(payload.client_id, user)
    if payload.target not in TARGET_FIELDS:
        raise HTTPException(400, f"Unknown target {payload.target}")

    collection = payload.target
    valid_fields = TARGET_FIELDS[collection]
    inserted = 0
    skipped = 0
    docs: List[dict] = []

    for row in payload.rows:
        cleaned = {}
        for field in valid_fields:
            if field in row and row[field] not in (None, "", "nan"):
                cleaned[field] = row[field]
        # Every target has one required key: name / firm_name / fy_end
        required = {"directors": "name", "auditors": "firm_name", "financials": "fy_end"}[collection]
        if not cleaned.get(required):
            skipped += 1
            continue
        cleaned.update({
            "id": str(uuid.uuid4()),
            "client_id": payload.client_id,
            "created_at": now_iso(),
            "source": "import",
        })
        docs.append(cleaned)
        inserted += 1

    if docs:
        await db[collection].insert_many([dict(d) for d in docs])
        await log_audit(payload.client_id, user, f"{collection}.imported",
                        f"Imported {inserted} row(s) from Excel", collection, "")

    return {"inserted": inserted, "skipped": skipped, "message": f"Imported {inserted} records"}


# ---------------------------------------------------------------------------
# Portfolio dashboard + reminders
# ---------------------------------------------------------------------------
@api.get("/dashboard")
async def dashboard(user=Depends(current_user)):
    clients = await db.clients.find({"owner_user_id": user["id"]}, {"_id": 0, "id": 1}).to_list(500)
    client_ids = [c["id"] for c in clients]
    if not client_ids:
        return {"clients": 0, "obligations": 0, "overdue": 0, "due_soon": 0,
                "completed": 0, "team_utilisation": 0}
    match = {"client_id": {"$in": client_ids}}
    total = await db.obligations.count_documents(match)
    overdue = await db.obligations.count_documents({**match, "status": "Overdue"})
    due_soon = await db.obligations.count_documents({**match, "status": "Due soon"})
    completed = await db.obligations.count_documents({**match, "status": "Completed"})
    return {
        "clients": len(client_ids),
        "obligations": total,
        "overdue": overdue,
        "due_soon": due_soon,
        "completed": completed,
        "team_utilisation": min(100, int((total - overdue) / max(1, total) * 100)),
    }


@api.get("/reminders")
async def reminders(user=Depends(current_user)):
    clients = await db.clients.find({"owner_user_id": user["id"]}, {"_id": 0}).to_list(500)
    client_map = {c["id"]: c for c in clients}
    if not client_map:
        return []
    rows = await db.obligations.find(
        {"client_id": {"$in": list(client_map)}, "status": {"$ne": "Completed"}},
        {"_id": 0},
    ).to_list(1000)
    for row in rows:
        client = client_map.get(row["client_id"], {})
        row["client_name"] = client.get("name", "")
        row["client_code"] = client.get("code", "")
    rows.sort(key=lambda r: r.get("due") or "")
    return rows[:200]


@api.post("/clients/demo")
async def create_demo_client(user=Depends(current_user)):
    """One-click demo client: full workspace with directors, shareholders, obligations."""
    count = await db.clients.count_documents({"owner_user_id": user["id"]})
    limit = int(user.get("client_limit", 5))
    if count >= limit:
        raise HTTPException(403, f"Your plan allows {limit} clients. Delete one before creating the demo.")
    client_id = str(uuid.uuid4())
    fy_now = datetime.now(timezone.utc)
    fy_start = fy_now.year if fy_now.month >= 4 else fy_now.year - 1
    fy = f"{fy_start}-{str((fy_start + 1) % 100).zfill(2)}"
    demo = {
        "id": client_id,
        "owner_user_id": user["id"],
        "name": "Sunrise Innovations Pvt Ltd",
        "code": "SUNRISE",
        "cin": "U72900MH2022PTC198765",
        "sector": "Private company",
        "state": "Maharashtra",
        "registered_address": "301, Andheri East, Mumbai 400069",
        "incorporation_date": "2022-06-14",
        "health": 76,
        "created_at": now_iso(),
        "is_demo": True,
    }
    await db.clients.insert_one(dict(demo))
    # Directors
    directors = [
        {"name": "Ananya Kapoor", "din": "08123456", "designation": "Managing Director", "appointment_date": "2022-06-14", "kyc_status": "Filed", "email": "ananya@sunrise.co", "pan": "ABCPK1234A"},
        {"name": "Rohit Menon", "din": "08234567", "designation": "Director", "appointment_date": "2022-06-14", "kyc_status": "Filed", "email": "rohit@sunrise.co", "pan": "ABCPM5678B"},
        {"name": "Sara Iyer", "din": "08345678", "designation": "CFO", "appointment_date": "2023-04-01", "kyc_status": "Pending", "email": "sara@sunrise.co", "pan": "ABCPI9012C"},
    ]
    for d in directors:
        await db.directors.insert_one({"id": str(uuid.uuid4()), "client_id": client_id, "created_at": now_iso(), "source": "demo", **d})
    # Auditors
    await db.auditors.insert_one({"id": str(uuid.uuid4()), "client_id": client_id, "created_at": now_iso(),
                                   "firm_name": "Sharma & Associates LLP", "frn": "123456W", "appointment_date": "2023-08-15", "term_end_date": "2028-08-14"})
    # Shareholders
    shareholders = [
        {"name": "Ananya Kapoor", "folio_no": "F-001", "shares_held": 60000, "share_class": "Equity", "date_of_holding": "2022-06-14"},
        {"name": "Rohit Menon", "folio_no": "F-002", "shares_held": 30000, "share_class": "Equity", "date_of_holding": "2022-06-14"},
        {"name": "Blume Ventures", "folio_no": "F-003", "shares_held": 10000, "share_class": "CCPS Series A", "date_of_holding": "2023-11-20"},
    ]
    for sh in shareholders:
        await db.shareholders.insert_one({"id": str(uuid.uuid4()), "client_id": client_id, "created_at": now_iso(), **sh})
    # A charge
    await db.charges.insert_one({"id": str(uuid.uuid4()), "client_id": client_id, "created_at": now_iso(),
                                  "charge_id": "CHG-001", "creation_date": "2023-03-11", "amount": 50000000,
                                  "holder": "HDFC Bank Ltd", "description": "Working capital facility", "status": "Open"})
    # A resolution
    await db.resolutions.insert_one({"id": str(uuid.uuid4()), "client_id": client_id, "created_at": now_iso(),
                                      "number": "BR-01/24", "passed_on": "2024-04-10",
                                      "resolution_type": "Board", "subject": "Approval of annual financial statements", "filing_form": "AOC-4"})
    # Financials
    await db.financials.insert_one({"id": str(uuid.uuid4()), "client_id": client_id, "created_at": now_iso(),
                                     "fy_end": "2025-03-31", "revenue": 45000000, "profit": 3200000,
                                     "net_worth": 12800000, "paid_up_capital": 1000000, "borrowings": 45000000, "turnover": 45000000, "listed": False})
    # Generate obligations for current FY
    generated = 0
    for rule in COMPLIANCE_RULES:
        due = resolve_due(fy, rule)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        status = "Overdue" if due < today else ("Due soon" if due <= (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d") else "On track")
        obligation = {
            "id": str(uuid.uuid4()), "client_id": client_id, "code": rule["code"], "name": rule["name"],
            "form": rule["form"], "section": rule["section"], "category": rule["category"],
            "priority": rule["priority"], "risk": "Watch", "recurrence": rule["recurrence"],
            "fy": fy, "due": due, "status": status, "assignee": "Unassigned",
            "reviewer": None, "filed_date": None, "srn": None, "remarks": "",
            "description": rule["description"], "created_at": now_iso(),
        }
        await db.obligations.insert_one(dict(obligation))
        generated += 1
    await log_audit(client_id, user, "client.demo_created",
                    f"Demo client created with {generated} obligations, {len(directors)} directors, {len(shareholders)} shareholders", "client", client_id)
    demo.pop("_id", None)
    return {"client": demo, "obligations": generated, "directors": len(directors), "shareholders": len(shareholders)}


# ---------------------------------------------------------------------------
# Recurring compliance engine
# ---------------------------------------------------------------------------
@api.get("/rules")
async def list_rules(user=Depends(current_user)):
    return COMPLIANCE_RULES


@api.post("/clients/{client_id}/generate-obligations")
async def generate_fy_obligations(client_id: str, payload: GenerateFyIn, user=Depends(current_user)):
    await ensure_owned_client(client_id, user)
    created, skipped = 0, 0
    for rule in COMPLIANCE_RULES:
        exists = await db.obligations.find_one({
            "client_id": client_id,
            "form": rule["form"],
            "section": rule["section"],
            "fy": payload.fy,
            "code": rule["code"],
        })
        if exists:
            skipped += 1
            continue
        due = resolve_due(payload.fy, rule)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        status = "Overdue" if due < today else ("Due soon" if due <= (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d") else "On track")
        item = {
            "id": str(uuid.uuid4()),
            "client_id": client_id,
            "code": rule["code"],
            "name": rule["name"],
            "form": rule["form"],
            "section": rule["section"],
            "category": rule["category"],
            "priority": rule["priority"],
            "risk": "Watch",
            "recurrence": rule["recurrence"],
            "fy": payload.fy,
            "due": due,
            "status": status,
            "assignee": "Unassigned",
            "reviewer": None,
            "filed_date": None,
            "srn": None,
            "remarks": "",
            "description": rule["description"],
            "created_at": now_iso(),
        }
        await db.obligations.insert_one(dict(item))
        created += 1
    if created:
        await log_audit(client_id, user, "obligations.generated",
                        f"Generated {created} obligations for FY {payload.fy}", "obligation", "")
    return {"created": created, "skipped": skipped, "fy": payload.fy}


# ---------------------------------------------------------------------------
# Statutory registers (additional master data)
# ---------------------------------------------------------------------------
list_shareholders, add_shareholder, remove_shareholder = _master_router("shareholders", ShareholderIn, "shareholder")
list_charges, add_charge, remove_charge = _master_router("charges", ChargeIn, "charge")
list_resolutions, add_resolution, remove_resolution = _master_router("resolutions", ResolutionIn, "resolution")
list_contracts, add_contract, remove_contract = _master_router("contracts", ContractIn, "contract")

for _entity in ("shareholders", "charges", "resolutions", "contracts"):
    _list_fn = {"shareholders": list_shareholders, "charges": list_charges,
                "resolutions": list_resolutions, "contracts": list_contracts}[_entity]
    _add_fn = {"shareholders": add_shareholder, "charges": add_charge,
               "resolutions": add_resolution, "contracts": add_contract}[_entity]
    _del_fn = {"shareholders": remove_shareholder, "charges": remove_charge,
               "resolutions": remove_resolution, "contracts": remove_contract}[_entity]
    api.add_api_route(f"/clients/{{client_id}}/{_entity}", _list_fn, methods=["GET"])
    api.add_api_route(f"/clients/{{client_id}}/{_entity}", _add_fn, methods=["POST"])
    api.add_api_route(f"/clients/{{client_id}}/{_entity}/{{item_id}}", _del_fn, methods=["DELETE"])


REGISTER_MAP = {
    "directors": ("Register of Directors and KMP (MBP-1)",
                  ["name", "din", "designation", "appointment_date", "cessation_date", "kyc_status", "email", "pan"]),
    "shareholders": ("Register of Members (MGT-1)",
                     ["name", "folio_no", "pan", "shares_held", "share_class", "date_of_holding", "email"]),
    "charges": ("Register of Charges (Section 85)",
                ["charge_id", "creation_date", "amount", "holder", "description", "status", "modification_date", "satisfaction_date"]),
    "resolutions": ("Register of Board & General Meeting Resolutions",
                    ["number", "passed_on", "resolution_type", "subject", "body", "filing_form"]),
    "contracts": ("Register of Contracts (MBP-4)",
                  ["counterparty", "relationship", "nature", "value", "start_date", "end_date", "approval_reference"]),
    "auditors": ("Register of Auditor Appointments",
                 ["firm_name", "frn", "appointment_date", "term_end_date", "email", "pan"]),
}


@api.get("/clients/{client_id}/registers/{register}.csv")
async def download_register(client_id: str, register: str, user=Depends(current_user)):
    from fastapi.responses import StreamingResponse
    import csv
    client = await ensure_owned_client(client_id, user)
    if register not in REGISTER_MAP:
        raise HTTPException(404, "Unknown register")
    title, fields = REGISTER_MAP[register]
    rows = await db[register].find({"client_id": client_id}, {"_id": 0}).to_list(1000)
    buf = io.StringIO()
    buf.write(f"{title}\nCompany: {client['name']}\nCIN: {client.get('cin') or 'N/A'}\nGenerated: {now_iso()}\n\n")
    writer = csv.writer(buf)
    writer.writerow([f.replace("_", " ").title() for f in fields])
    for row in rows:
        writer.writerow([row.get(f, "") for f in fields])
    buf.seek(0)
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{register}-{client["code"]}.csv"',
    })


@api.get("/clients/{client_id}/registers")
async def list_registers(client_id: str, user=Depends(current_user)):
    await ensure_owned_client(client_id, user)
    out = []
    for key, (title, fields) in REGISTER_MAP.items():
        count = await db[key].count_documents({"client_id": client_id})
        out.append({"key": key, "title": title, "fields": fields, "count": count})
    return out


# ---------------------------------------------------------------------------
# Notifications (T-30 / T-7 / T-1 / Overdue)
# ---------------------------------------------------------------------------
@api.get("/notifications")
async def notifications(user=Depends(current_user)):
    clients = await db.clients.find({"owner_user_id": user["id"]}, {"_id": 0}).to_list(500)
    client_map = {c["id"]: c for c in clients}
    if not client_map:
        return {"items": [], "counts": {"overdue": 0, "t1": 0, "t7": 0, "t30": 0}}
    rows = await db.obligations.find(
        {"client_id": {"$in": list(client_map)}, "status": {"$nin": ["Completed", "Approved"]}},
        {"_id": 0},
    ).to_list(2000)
    today = datetime.now(timezone.utc).date()
    items, counts = [], {"overdue": 0, "t1": 0, "t7": 0, "t30": 0}
    dismissed = set()
    async for d in db.notifications_dismissed.find({"user_id": user["id"]}, {"_id": 0, "obligation_id": 1}):
        dismissed.add(d["obligation_id"])
    for row in rows:
        if row["id"] in dismissed or not row.get("due"):
            continue
        try:
            due = datetime.strptime(row["due"], "%Y-%m-%d").date()
        except ValueError:
            continue
        delta = (due - today).days
        if delta < 0:
            bucket, tone = "overdue", "danger"
        elif delta <= 1:
            bucket, tone = "t1", "danger"
        elif delta <= 7:
            bucket, tone = "t7", "warning"
        elif delta <= 30:
            bucket, tone = "t30", "warning"
        else:
            continue
        counts[bucket] += 1
        client = client_map.get(row["client_id"], {})
        items.append({
            "id": row["id"],
            "client_name": client.get("name", ""),
            "client_id": row["client_id"],
            "form": row["form"],
            "name": row["name"],
            "due": row["due"],
            "days": delta,
            "bucket": bucket,
            "tone": tone,
            "assignee": row.get("assignee"),
            "status": row["status"],
        })
    items.sort(key=lambda x: x["days"])
    return {"items": items[:100], "counts": counts}


@api.post("/notifications/{obligation_id}/dismiss")
async def dismiss_notification(obligation_id: str, user=Depends(current_user)):
    await db.notifications_dismissed.update_one(
        {"user_id": user["id"], "obligation_id": obligation_id},
        {"$set": {"dismissed_at": now_iso()}},
        upsert=True,
    )
    return {"message": "Dismissed"}


# ---------------------------------------------------------------------------
# Maker-checker workflow
# ---------------------------------------------------------------------------
@api.patch("/obligations/{obligation_id}/submit")
async def submit_for_review(obligation_id: str, payload: SubmitIn, user=Depends(current_user)):
    row = await db.obligations.find_one({"id": obligation_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Obligation not found")
    await ensure_owned_client(row["client_id"], user)
    if row.get("assignee") and row["assignee"] not in ("Unassigned", user["name"], user["email"]):
        # allow anyway but log — owners often need to submit on behalf of team
        pass
    await db.obligations.update_one(
        {"id": obligation_id},
        {"$set": {"status": "Ready for review", "submitted_by": user["name"],
                  "submitted_at": now_iso(), "review_remarks": payload.remarks or ""}},
    )
    await log_audit(row["client_id"], user, "obligation.submitted",
                    f"Submitted {row['form']} for review", "obligation", obligation_id)
    return strip(await db.obligations.find_one({"id": obligation_id}, {"_id": 0}))


@api.patch("/obligations/{obligation_id}/review")
async def review_obligation(obligation_id: str, payload: ReviewIn, user=Depends(current_user)):
    row = await db.obligations.find_one({"id": obligation_id}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Obligation not found")
    await ensure_owned_client(row["client_id"], user)
    if row.get("status") != "Ready for review":
        raise HTTPException(400, "Only obligations submitted for review can be actioned")
    if row.get("submitted_by") == user["name"] and user.get("role") != "owner":
        raise HTTPException(403, "The submitter cannot be their own reviewer")
    new_status = "Approved" if payload.approved else "Rework"
    await db.obligations.update_one(
        {"id": obligation_id},
        {"$set": {"status": new_status, "reviewed_by": user["name"],
                  "reviewed_at": now_iso(), "review_remarks": payload.remarks or ""}},
    )
    await log_audit(row["client_id"], user,
                    "obligation.approved" if payload.approved else "obligation.rework",
                    f"{'Approved' if payload.approved else 'Sent back for rework'}: {row['form']}",
                    "obligation", obligation_id)
    return strip(await db.obligations.find_one({"id": obligation_id}, {"_id": 0}))


# ---------------------------------------------------------------------------
# Mount
# ---------------------------------------------------------------------------
app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=[os.environ.get("FRONTEND_URL", "*")],
    allow_methods=["*"],
    allow_headers=["*"],
)
logging.basicConfig(level=logging.INFO)


@app.on_event("startup")
async def indexes():
    await db.users.create_index("email", unique=True)
    await db.clients.create_index("owner_user_id")
    await db.obligations.create_index("client_id")
    await db.audit_log.create_index([("client_id", 1), ("created_at", -1)])
    # One-time cleanup: remove legacy auto-seeded obligations (pre rule-engine, no `code` field)
    await db.obligations.delete_many({"code": {"$exists": False}})


@app.on_event("shutdown")
async def close_db():
    mongo.close()
