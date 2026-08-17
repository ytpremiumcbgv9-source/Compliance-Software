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
SEED_OBLIGATIONS = [
    {"name": "Annual return filing", "form": "MGT-7", "section": "92", "category": "Annual filing",
     "due": "2026-09-30", "assignee": "Unassigned", "status": "Due soon", "priority": "High",
     "risk": "Watch", "description": "Annual return with prescribed particulars and financial disclosures."},
    {"name": "Financial statements filing", "form": "AOC-4", "section": "137", "category": "Annual filing",
     "due": "2026-10-29", "assignee": "Unassigned", "status": "On track", "priority": "Critical",
     "risk": "Low", "description": "File adopted financial statements with the Registrar."},
    {"name": "Director KYC", "form": "DIR-3 KYC", "section": "164", "category": "Directors",
     "due": "2026-09-30", "assignee": "Unassigned", "status": "Overdue", "priority": "Critical",
     "risk": "High", "description": "Complete annual KYC for every active director."},
    {"name": "Board meetings", "form": "BM Calendar", "section": "173", "category": "Governance",
     "due": "2026-06-30", "assignee": "Unassigned", "status": "Under review", "priority": "Medium",
     "risk": "Watch", "description": "Maintain the required meeting cadence and minutes."},
    {"name": "Auditor appointment", "form": "ADT-1", "section": "139", "category": "Audit",
     "due": "2026-07-14", "assignee": "Unassigned", "status": "On track", "priority": "High",
     "risk": "Low", "description": "Record auditor appointment and retain consent evidence."},
    {"name": "DPT-3 return", "form": "DPT-3", "section": "73", "category": "Deposits",
     "due": "2026-06-30", "assignee": "Unassigned", "status": "On track", "priority": "Medium",
     "risk": "Watch", "description": "Return of deposits and outstanding money not treated as deposits."},
    {"name": "MSME-1 half-yearly", "form": "MSME-1", "section": "405", "category": "MSME",
     "due": "2026-10-31", "assignee": "Unassigned", "status": "On track", "priority": "Medium",
     "risk": "Low", "description": "Half-yearly return of outstanding MSME payments beyond 45 days."},
]

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
    if not rows:
        rows = [{
            **item, "id": str(uuid.uuid4()), "client_id": client_id,
            "filed_date": None, "srn": None, "remarks": "",
        } for item in SEED_OBLIGATIONS]
        await db.obligations.insert_many([dict(x) for x in rows])
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


@app.on_event("shutdown")
async def close_db():
    mongo.close()
