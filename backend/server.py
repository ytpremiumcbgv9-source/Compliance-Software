from fastapi import FastAPI, APIRouter, UploadFile, File, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, ConfigDict
from pathlib import Path
from datetime import datetime, timezone, date, timedelta
from typing import Optional, List
import os, uuid, logging

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")
mongo = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = mongo[os.environ["DB_NAME"]]
app = FastAPI(title="ComplyEase API")
api = APIRouter(prefix="/api")

class ClientIn(BaseModel):
    name: str
    code: str
    sector: str = "Private company"
    state: str = "Maharashtra"

class Client(ClientIn):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    health: int = 0
    open_items: int = 0
    overdue: int = 0

class ObligationUpdate(BaseModel):
    status: str
    filed_date: Optional[str] = None
    srn: Optional[str] = None

def clean(doc):
    doc.pop("_id", None)
    return doc

SEED_OBLIGATIONS = [
    {"name":"Annual return filing", "form":"MGT-7", "section":"92", "category":"Annual filing", "due":"2026-09-30", "owner":"A. Mehta", "status":"Due soon", "priority":"High", "risk":"Watch", "description":"Annual return with prescribed particulars and financial disclosures."},
    {"name":"Financial statements filing", "form":"AOC-4", "section":"137", "category":"Annual filing", "due":"2026-10-29", "owner":"R. Shah", "status":"On track", "priority":"Critical", "risk":"Low", "description":"File adopted financial statements with the Registrar."},
    {"name":"Director KYC", "form":"DIR-3 KYC", "section":"164", "category":"Directors", "due":"2026-09-30", "owner":"A. Mehta", "status":"Overdue", "priority":"Critical", "risk":"High", "description":"Complete annual KYC for every active director."},
    {"name":"Board meetings", "form":"BM calendar", "section":"173", "category":"Governance", "due":"2026-06-30", "owner":"S. Iyer", "status":"Under review", "priority":"Medium", "risk":"Watch", "description":"Maintain required meeting cadence and minutes."},
    {"name":"Auditor appointment", "form":"ADT-1", "section":"139", "category":"Audit", "due":"2026-07-14", "owner":"R. Shah", "status":"On track", "priority":"High", "risk":"Low", "description":"Record auditor appointment and retain consent evidence."},
]

@api.get("/")
async def root(): return {"message":"ComplyEase API ready"}

@api.get("/clients", response_model=List[Client])
async def clients():
    rows = await db.clients.find({}, {"_id": 0}).to_list(100)
    if not rows:
        seed = [Client(name="Northstar Textiles Pvt Ltd", code="NST-001", sector="Manufacturing", state="Maharashtra", health=82, open_items=12, overdue=2).model_dump(), Client(name="Pioneer Health Systems", code="PHS-014", sector="Healthcare", state="Karnataka", health=94, open_items=5, overdue=0).model_dump(), Client(name="BluePeak Logistics", code="BPL-022", sector="Logistics", state="Delhi", health=67, open_items=19, overdue=5).model_dump()]
        await db.clients.insert_many(seed); rows = seed
    return rows

@api.post("/clients", response_model=Client)
async def create_client(payload: ClientIn):
    item = Client(**payload.model_dump()).model_dump()
    await db.clients.insert_one(item); return item

@api.get("/clients/{client_id}/obligations")
async def obligations(client_id: str):
    rows = await db.obligations.find({"client_id": client_id}, {"_id": 0}).to_list(500)
    if not rows:
        rows = [{**x, "id": str(uuid.uuid4()), "client_id": client_id, "filed_date": None, "srn": None} for x in SEED_OBLIGATIONS]
        await db.obligations.insert_many([dict(x) for x in rows])
        rows = await db.obligations.find({"client_id": client_id}, {"_id": 0}).to_list(500)
    return rows

@api.patch("/obligations/{obligation_id}")
async def update_obligation(obligation_id: str, payload: ObligationUpdate):
    result = await db.obligations.update_one({"id": obligation_id}, {"$set": payload.model_dump(exclude_none=True)})
    if not result.matched_count: raise HTTPException(404, "Obligation not found")
    row = await db.obligations.find_one({"id": obligation_id}, {"_id": 0})
    return row

@api.post("/clients/{client_id}/evidence")
async def upload_evidence(client_id: str, file: UploadFile = File(...)):
    record = {"id": str(uuid.uuid4()), "client_id": client_id, "filename": file.filename, "content_type": file.content_type, "uploaded_at": datetime.now(timezone.utc).isoformat(), "uploaded_by": "PCS workspace"}
    await db.evidence.insert_one(record)
    return clean(record)

@api.get("/clients/{client_id}/activity")
async def activity(client_id: str):
    evidence = await db.evidence.find({"client_id": client_id}, {"_id": 0}).sort("uploaded_at", -1).to_list(20)
    return [{"label": "Evidence added", "detail": x["filename"], "time": x["uploaded_at"]} for x in evidence]

app.include_router(api)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])
logging.basicConfig(level=logging.INFO)

@app.on_event("shutdown")
async def close_db(): mongo.close()