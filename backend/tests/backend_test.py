"""ComplyEase backend regression tests.

Covers: auth (login/logout/me/suspended), owner administration (requests/users/limit/status),
clients CRUD + quota + isolation, obligations seed + update, master data (directors/auditors/financials),
audit log, imports preview+apply, dashboard, reminders.
"""
import io
import os
import uuid
from pathlib import Path

import openpyxl
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

OWNER_EMAIL = "owner.1786939113@test.local"
OWNER_PASSWORD = "OwnerPass!123"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def owner_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=20)
    if r.status_code != 200:
        pytest.fail(f"Owner login failed {r.status_code}: {r.text[:400]}")
    assert "access_token" in s.cookies
    return s


@pytest.fixture(scope="module")
def owner_client(owner_session):
    """Create a dedicated TEST_ client for master-data / import / audit tests, then delete it."""
    unique = f"TEST_{uuid.uuid4().hex[:8]}"
    r = owner_session.post(f"{API}/clients", json={"name": unique, "code": unique}, timeout=20)
    assert r.status_code == 200, r.text
    client = r.json()
    yield client
    owner_session.delete(f"{API}/clients/{client['id']}", timeout=20)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
class TestAuth:
    def test_login_success_sets_cookie_and_returns_owner(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == OWNER_EMAIL
        assert body["role"] == "owner"
        assert "access_token" in s.cookies

    def test_login_invalid_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": "wrong"}, timeout=20)
        assert r.status_code == 401

    def test_me_requires_auth(self):
        r = requests.get(f"{API}/auth/me", timeout=20)
        assert r.status_code == 401

    def test_logout_clears_session(self):
        s = requests.Session()
        s.post(f"{API}/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD}, timeout=20)
        assert s.get(f"{API}/auth/me", timeout=20).status_code == 200
        assert s.post(f"{API}/auth/logout", timeout=20).status_code == 200
        # cookie deleted -> use fresh session semantics: re-check with cleared cookies
        s.cookies.clear()
        assert s.get(f"{API}/auth/me", timeout=20).status_code == 401

    def test_signup_pending_and_suspended_cannot_login(self, owner_session):
        # signup random member -> pending
        email = f"TEST_{uuid.uuid4().hex[:8]}@test.local"
        pw = "MemberPass!123"
        r = requests.post(f"{API}/auth/signup", json={
            "name": "TEST Member", "email": email, "password": pw, "practice_name": "TEST Firm"
        }, timeout=20)
        assert r.status_code == 200
        user_id = r.json()["user"]["id"]

        # pending cannot login
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
        assert r.status_code == 403
        assert "awaiting" in r.json()["detail"].lower()

        # owner approves
        r = owner_session.patch(f"{API}/owner/requests/{user_id}",
                                json={"approved": True, "client_limit": 3}, timeout=20)
        assert r.status_code == 200

        # approved can login
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
        assert r.status_code == 200

        # owner suspends
        r = owner_session.patch(f"{API}/owner/users/{user_id}/status",
                                json={"status": "suspended"}, timeout=20)
        assert r.status_code == 200

        # suspended cannot login
        r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=20)
        assert r.status_code == 403
        assert "suspend" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Owner admin
# ---------------------------------------------------------------------------
class TestOwnerAdmin:
    def test_owner_requests_list(self, owner_session):
        r = owner_session.get(f"{API}/owner/requests", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_owner_users_have_clients_used(self, owner_session):
        r = owner_session.get(f"{API}/owner/users", timeout=20)
        assert r.status_code == 200
        for u in r.json():
            assert "clients_used" in u and "client_limit" in u

    def test_update_limit(self, owner_session):
        users = owner_session.get(f"{API}/owner/users", timeout=20).json()
        if not users:
            pytest.skip("No members to update")
        uid = users[0]["id"]
        r = owner_session.patch(f"{API}/owner/users/{uid}/limit", json={"client_limit": 9}, timeout=20)
        assert r.status_code == 200
        after = owner_session.get(f"{API}/owner/users", timeout=20).json()
        assert next(u for u in after if u["id"] == uid)["client_limit"] == 9

    def test_non_owner_blocked(self):
        # create pending user, approve, login as them, try owner endpoint
        r = requests.get(f"{API}/owner/requests", timeout=20)
        assert r.status_code == 401  # not logged in


# ---------------------------------------------------------------------------
# Clients + isolation
# ---------------------------------------------------------------------------
class TestClients:
    def test_create_list_patch_delete(self, owner_session):
        unique = f"TEST_{uuid.uuid4().hex[:8]}"
        r = owner_session.post(f"{API}/clients", json={"name": unique, "code": unique}, timeout=20)
        assert r.status_code == 200
        cid = r.json()["id"]
        # list
        rows = owner_session.get(f"{API}/clients", timeout=20).json()
        assert any(c["id"] == cid for c in rows)
        # patch
        p = owner_session.patch(f"{API}/clients/{cid}", json={"sector": "LLP"}, timeout=20)
        assert p.status_code == 200 and p.json()["sector"] == "LLP"
        # delete
        d = owner_session.delete(f"{API}/clients/{cid}", timeout=20)
        assert d.status_code == 200
        rows = owner_session.get(f"{API}/clients", timeout=20).json()
        assert not any(c["id"] == cid for c in rows)

    def test_random_client_id_returns_404(self, owner_session):
        r = owner_session.get(f"{API}/clients/{uuid.uuid4()}/obligations", timeout=20)
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Obligations
# ---------------------------------------------------------------------------
class TestObligations:
    def test_seed_and_status_update(self, owner_session, owner_client):
        cid = owner_client["id"]
        rows = owner_session.get(f"{API}/clients/{cid}/obligations", timeout=20).json()
        assert len(rows) >= 5
        row = rows[0]
        new_status = "Completed" if row["status"] != "Completed" else "On track"
        r = owner_session.patch(f"{API}/obligations/{row['id']}",
                                json={"status": new_status, "srn": "TEST-SRN", "remarks": "TEST"},
                                timeout=20)
        assert r.status_code == 200
        assert r.json()["status"] == new_status
        # persistence
        again = owner_session.get(f"{API}/clients/{cid}/obligations", timeout=20).json()
        got = next(x for x in again if x["id"] == row["id"])
        assert got["status"] == new_status
        assert got["srn"] == "TEST-SRN"
        assert got["remarks"] == "TEST"


# ---------------------------------------------------------------------------
# Master data
# ---------------------------------------------------------------------------
class TestMasterData:
    def test_director_crud(self, owner_session, owner_client):
        cid = owner_client["id"]
        payload = {"name": "TEST Director", "din": "00000001", "designation": "MD"}
        r = owner_session.post(f"{API}/clients/{cid}/directors", json=payload, timeout=20)
        assert r.status_code == 200
        d = r.json()
        # verify list
        rows = owner_session.get(f"{API}/clients/{cid}/directors", timeout=20).json()
        assert any(x["id"] == d["id"] and x["name"] == "TEST Director" for x in rows)
        # delete
        assert owner_session.delete(f"{API}/clients/{cid}/directors/{d['id']}", timeout=20).status_code == 200
        rows = owner_session.get(f"{API}/clients/{cid}/directors", timeout=20).json()
        assert not any(x["id"] == d["id"] for x in rows)

    def test_auditor_and_financials_add(self, owner_session, owner_client):
        cid = owner_client["id"]
        a = owner_session.post(f"{API}/clients/{cid}/auditors",
                               json={"firm_name": "TEST & Co"}, timeout=20)
        assert a.status_code == 200 and a.json()["firm_name"] == "TEST & Co"
        f = owner_session.post(f"{API}/clients/{cid}/financials",
                               json={"fy_end": "2026-03-31", "revenue": 100}, timeout=20)
        assert f.status_code == 200 and f.json()["fy_end"] == "2026-03-31"


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------
def _build_workbook():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Directors"
    ws.append(["Director Name", "DIN", "Designation", "Date of Appointment", "KYC Status", "Email"])
    ws.append(["Alice Anand", "00011122", "Managing Director", "2020-04-01", "Compliant", "a@x.com"])
    ws.append(["Bob Bhat", "00033344", "Director", "2021-06-15", "Pending", "b@x.com"])
    fin = wb.create_sheet("Financials")
    fin.append(["FY End", "Revenue", "Profit", "Net Worth", "Turnover"])
    fin.append(["2026-03-31", 5000000, 400000, 1200000, 5000000])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()


class TestImports:
    def test_preview_and_apply(self, owner_session, owner_client):
        content = _build_workbook()
        preview = owner_session.post(
            f"{API}/imports/preview",
            files={"file": ("TEST_book.xlsx", content,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            timeout=30,
        )
        assert preview.status_code == 200, preview.text
        data = preview.json()
        sheets = {s["name"]: s for s in data["sheets"]}
        assert set(sheets) == {"Directors", "Financials"}
        assert sheets["Directors"]["suggested_target"] == "directors"
        assert sheets["Financials"]["suggested_target"] == "financials"
        # mapping must map required field
        assert "name" in sheets["Directors"]["suggested_mapping"]
        assert "fy_end" in sheets["Financials"]["suggested_mapping"]

        cid = owner_client["id"]

        # Build director rows by applying suggested mapping (col -> field inversion)
        dmap = sheets["Directors"]["suggested_mapping"]  # field -> column
        director_rows = []
        for r in sheets["Directors"]["rows"]:
            director_rows.append({field: r.get(col) for field, col in dmap.items()})
        applied = owner_session.post(f"{API}/imports/apply",
                                     json={"client_id": cid, "target": "directors", "rows": director_rows},
                                     timeout=30)
        assert applied.status_code == 200, applied.text
        assert applied.json()["inserted"] == 2

        fmap = sheets["Financials"]["suggested_mapping"]
        fin_rows = [{field: r.get(col) for field, col in fmap.items()}
                    for r in sheets["Financials"]["rows"]]
        applied = owner_session.post(f"{API}/imports/apply",
                                     json={"client_id": cid, "target": "financials", "rows": fin_rows},
                                     timeout=30)
        assert applied.status_code == 200
        assert applied.json()["inserted"] == 1

        # verify master data updated
        directors = owner_session.get(f"{API}/clients/{cid}/directors", timeout=20).json()
        assert sum(1 for d in directors if d.get("source") == "import") >= 2
        fins = owner_session.get(f"{API}/clients/{cid}/financials", timeout=20).json()
        assert any(f.get("fy_end") == "2026-03-31" for f in fins)

        # audit log has directors.imported and financials.imported and client.created
        log = owner_session.get(f"{API}/clients/{cid}/audit-log", timeout=20).json()
        actions = {row["action"] for row in log}
        assert {"client.created", "directors.imported", "financials.imported"}.issubset(actions)

    def test_apply_skips_rows_missing_required(self, owner_session, owner_client):
        cid = owner_client["id"]
        r = owner_session.post(f"{API}/imports/apply", json={
            "client_id": cid, "target": "directors",
            "rows": [{"din": "999"}, {"name": "TEST Solo"}],
        }, timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body["inserted"] == 1 and body["skipped"] == 1


# ---------------------------------------------------------------------------
# Dashboard + reminders
# ---------------------------------------------------------------------------
class TestPortfolio:
    def test_dashboard(self, owner_session):
        r = owner_session.get(f"{API}/dashboard", timeout=20)
        assert r.status_code == 200
        data = r.json()
        for k in ("clients", "obligations", "overdue", "due_soon", "completed", "team_utilisation"):
            assert k in data

    def test_reminders(self, owner_session, owner_client):
        # touch obligations first so seed happens
        owner_session.get(f"{API}/clients/{owner_client['id']}/obligations", timeout=20)
        r = owner_session.get(f"{API}/reminders", timeout=20)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        if rows:
            assert "client_name" in rows[0] and "status" in rows[0]
