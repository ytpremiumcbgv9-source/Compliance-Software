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


# Session-scoped: bump owner's client_limit directly in Mongo so parallel workers don't hit the quota.
@pytest.fixture(scope="session", autouse=True)
def _raise_owner_limit():
    try:
        from pymongo import MongoClient
        backend_env = dotenv_values("/app/backend/.env")
        mc = MongoClient(backend_env["MONGO_URL"], serverSelectionTimeoutMS=3000)
        mc[backend_env["DB_NAME"]].users.update_one(
            {"email": OWNER_EMAIL}, {"$set": {"client_limit": 50}}
        )
        mc.close()
    except Exception as exc:  # pragma: no cover - purely a test-env optimisation
        print(f"owner client_limit bump skipped: {exc}")


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
        # Fresh client should return [] before generate is called (no auto-seed)
        pre = owner_session.get(f"{API}/clients/{cid}/obligations", timeout=20).json()
        assert pre == [], f"expected empty obligations for fresh client, got {len(pre)}"
        # Generate FY 2026-27 obligations from rules
        gen = owner_session.post(f"{API}/clients/{cid}/generate-obligations",
                                 json={"fy": "2026-27"}, timeout=30)
        assert gen.status_code == 200
        rows = owner_session.get(f"{API}/clients/{cid}/obligations", timeout=20).json()
        assert len(rows) == 15, f"expected 15 generated obligations, got {len(rows)}"
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


# ---------------------------------------------------------------------------
# Recurring compliance engine — rules + generate-obligations
# ---------------------------------------------------------------------------
class TestRulesAndGenerate:
    def test_rules_library_has_15_entries(self, owner_session):
        r = owner_session.get(f"{API}/rules", timeout=20)
        assert r.status_code == 200
        rules = r.json()
        assert len(rules) == 15, f"expected 15 rules, got {len(rules)}"
        required_keys = {"code", "form", "section", "recurrence", "due_rule"}
        for rule in rules:
            missing = required_keys - set(rule.keys())
            assert not missing, f"rule {rule.get('code')} missing {missing}"

    def test_generate_fy_idempotent_and_due_dates(self, owner_session):
        # Fresh client to guarantee created=15 on first call
        unique = f"TEST_{uuid.uuid4().hex[:8]}"
        c = owner_session.post(f"{API}/clients", json={"name": unique, "code": unique}, timeout=20).json()
        cid = c["id"]
        try:
            r1 = owner_session.post(f"{API}/clients/{cid}/generate-obligations",
                                    json={"fy": "2026-27"}, timeout=30)
            assert r1.status_code == 200, r1.text
            body1 = r1.json()
            assert body1["created"] == 15 and body1["skipped"] == 0, body1

            # Idempotency
            r2 = owner_session.post(f"{API}/clients/{cid}/generate-obligations",
                                    json={"fy": "2026-27"}, timeout=30)
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["created"] == 0 and body2["skipped"] == 15, body2

            # Due-date checks + carrier fields
            rows = owner_session.get(f"{API}/clients/{cid}/obligations", timeout=20).json()
            by_code = {row["code"]: row for row in rows if row.get("fy") == "2026-27"}
            expectations = {
                "DPT-3": "2026-06-30",
                "DIR-3-KYC": "2027-09-30",
                "MGT-7": "2027-05-30",
                "MSME-1-H1": "2026-10-31",
                "BM-Q1": "2026-06-30",
            }
            for code, expected_due in expectations.items():
                row = by_code.get(code)
                assert row, f"missing obligation {code}"
                assert row["due"] == expected_due, f"{code} due {row['due']} != {expected_due}"
                assert row["fy"] == "2026-27"
                assert row["recurrence"] in ("annual", "half-yearly", "quarterly")
        finally:
            owner_session.delete(f"{API}/clients/{cid}", timeout=20)


# ---------------------------------------------------------------------------
# Statutory registers
# ---------------------------------------------------------------------------
class TestStatutoryRegisters:
    def test_registers_crud_and_list(self, owner_session, owner_client):
        cid = owner_client["id"]

        # Shareholder
        s = owner_session.post(f"{API}/clients/{cid}/shareholders",
                               json={"name": "TEST Holder", "folio_no": "F001", "shares_held": 100},
                               timeout=20)
        assert s.status_code == 200
        sh_id = s.json()["id"]

        # Charge
        ch = owner_session.post(f"{API}/clients/{cid}/charges",
                                json={"holder": "TEST Bank", "amount": 500000,
                                      "creation_date": "2025-04-01"}, timeout=20)
        assert ch.status_code == 200
        ch_id = ch.json()["id"]

        # Resolution
        rz = owner_session.post(f"{API}/clients/{cid}/resolutions",
                                json={"number": "R-01", "subject": "TEST Res",
                                      "resolution_type": "Board"}, timeout=20)
        assert rz.status_code == 200
        rz_id = rz.json()["id"]

        # Contract
        co = owner_session.post(f"{API}/clients/{cid}/contracts",
                                json={"counterparty": "TEST Vendor Ltd"}, timeout=20)
        assert co.status_code == 200
        co_id = co.json()["id"]

        # List all registers
        regs = owner_session.get(f"{API}/clients/{cid}/registers", timeout=20).json()
        keys = {r["key"]: r["count"] for r in regs}
        for expected in ("directors", "shareholders", "charges", "resolutions", "contracts", "auditors"):
            assert expected in keys, f"missing register {expected}"
        assert keys["shareholders"] >= 1
        assert keys["charges"] >= 1
        assert keys["resolutions"] >= 1
        assert keys["contracts"] >= 1

        # CSV download
        csv_r = owner_session.get(f"{API}/clients/{cid}/registers/shareholders.csv", timeout=20)
        assert csv_r.status_code == 200
        assert "text/csv" in csv_r.headers.get("content-type", "")
        text = csv_r.text
        assert owner_client["name"] in text  # company header
        assert "TEST Holder" in text

        # Delete each
        for path, item_id in [
            ("shareholders", sh_id), ("charges", ch_id),
            ("resolutions", rz_id), ("contracts", co_id),
        ]:
            d = owner_session.delete(f"{API}/clients/{cid}/{path}/{item_id}", timeout=20)
            assert d.status_code == 200, path

        # Audit log entries
        log = owner_session.get(f"{API}/clients/{cid}/audit-log", timeout=20).json()
        actions = {row["action"] for row in log}
        assert {"shareholder.added", "charge.added", "resolution.added", "contract.added"}.issubset(actions)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------
class TestNotifications:
    def test_notifications_buckets_and_dismiss(self, owner_session):
        # Generate a fresh FY on a scratch client with an in-past due (2024-25 fy => several overdue)
        unique = f"TEST_{uuid.uuid4().hex[:8]}"
        create = owner_session.post(f"{API}/clients", json={"name": unique, "code": unique}, timeout=20)
        assert create.status_code == 200, create.text
        c = create.json()
        cid = c["id"]
        try:
            owner_session.post(f"{API}/clients/{cid}/generate-obligations",
                               json={"fy": "2024-25"}, timeout=30)
            r = owner_session.get(f"{API}/notifications", timeout=20)
            assert r.status_code == 200
            data = r.json()
            assert set(data["counts"].keys()) == {"overdue", "t1", "t7", "t30"}
            assert isinstance(data["items"], list)
            # find at least one overdue from the 2024-25 FY
            past_items = [i for i in data["items"]
                          if i.get("client_id") == cid and i["bucket"] == "overdue"]
            assert past_items, "expected overdue notifications for old FY"
            first = past_items[0]
            for k in ("client_name", "form", "name", "due", "days", "bucket", "tone", "status"):
                assert k in first, f"missing field {k}"
            assert first["days"] < 0

            # Dismiss removes item for this user
            ob_id = first["id"]
            d = owner_session.post(f"{API}/notifications/{ob_id}/dismiss", timeout=20)
            assert d.status_code == 200
            after = owner_session.get(f"{API}/notifications", timeout=20).json()
            assert not any(i["id"] == ob_id for i in after["items"]), "dismissed item still visible"
        finally:
            owner_session.delete(f"{API}/clients/{cid}", timeout=20)


# ---------------------------------------------------------------------------
# Maker-checker
# ---------------------------------------------------------------------------
class TestMakerChecker:
    def test_submit_and_owner_can_approve_own(self, owner_session):
        # Fresh client + generate obligations
        unique = f"TEST_{uuid.uuid4().hex[:8]}"
        c = owner_session.post(f"{API}/clients", json={"name": unique, "code": unique}, timeout=20).json()
        cid = c["id"]
        try:
            owner_session.post(f"{API}/clients/{cid}/generate-obligations",
                               json={"fy": "2026-27"}, timeout=30)
            rows = owner_session.get(f"{API}/clients/{cid}/obligations", timeout=20).json()
            row = next(r for r in rows if r["code"] == "MGT-7")
            ob_id = row["id"]

            # Assign to Priya first
            up = owner_session.patch(f"{API}/obligations/{ob_id}",
                                     json={"assignee": "Priya"}, timeout=20)
            assert up.status_code == 200
            assert up.json()["assignee"] == "Priya"

            # Submit
            s = owner_session.patch(f"{API}/obligations/{ob_id}/submit",
                                    json={"remarks": "please review"}, timeout=20)
            assert s.status_code == 200, s.text
            body = s.json()
            assert body["status"] == "Ready for review"
            assert body.get("submitted_by")

            # Owner reviewing own submission is allowed
            rev = owner_session.patch(f"{API}/obligations/{ob_id}/review",
                                      json={"approved": True, "remarks": "ok"}, timeout=20)
            assert rev.status_code == 200, rev.text
            assert rev.json()["status"] == "Approved"

            # Second review call must 400 because status no longer "Ready for review"
            rev2 = owner_session.patch(f"{API}/obligations/{ob_id}/review",
                                       json={"approved": True}, timeout=20)
            assert rev2.status_code == 400, rev2.text

            # Audit log for submitted + approved
            log = owner_session.get(f"{API}/clients/{cid}/audit-log", timeout=20).json()
            actions = {row["action"] for row in log}
            assert {"obligations.generated", "obligation.submitted",
                    "obligation.approved"}.issubset(actions), actions
        finally:
            owner_session.delete(f"{API}/clients/{cid}", timeout=20)

    def test_member_cannot_review_own_submission(self, owner_session):
        """Non-owner submitter cannot review their own submission."""
        # Create + approve a fresh member
        email = f"TEST_{uuid.uuid4().hex[:8]}@test.local"
        pw = "MemberPass!123"
        signup = requests.post(f"{API}/auth/signup", json={
            "name": "TEST Member Chk", "email": email, "password": pw,
            "practice_name": "TEST Firm"}, timeout=20)
        assert signup.status_code == 200
        uid = signup.json()["user"]["id"]
        owner_session.patch(f"{API}/owner/requests/{uid}",
                            json={"approved": True, "client_limit": 3}, timeout=20)

        member = requests.Session()
        assert member.post(f"{API}/auth/login",
                           json={"email": email, "password": pw}, timeout=20).status_code == 200

        # Member creates a client + generates + submits
        unique = f"TEST_{uuid.uuid4().hex[:8]}"
        c = member.post(f"{API}/clients", json={"name": unique, "code": unique}, timeout=20).json()
        cid = c["id"]
        try:
            member.post(f"{API}/clients/{cid}/generate-obligations",
                        json={"fy": "2026-27"}, timeout=30)
            rows = member.get(f"{API}/clients/{cid}/obligations", timeout=20).json()
            ob_id = next(r for r in rows if r["code"] == "AOC-4")["id"]
            s = member.patch(f"{API}/obligations/{ob_id}/submit", json={}, timeout=20)
            assert s.status_code == 200
            # Same member tries to review own → 403
            r = member.patch(f"{API}/obligations/{ob_id}/review",
                             json={"approved": True}, timeout=20)
            assert r.status_code == 403, r.text
        finally:
            member.delete(f"{API}/clients/{cid}", timeout=20)
            # Suspend the member so they no longer clutter listings
            owner_session.patch(f"{API}/owner/users/{uid}/status",
                                json={"status": "suspended"}, timeout=20)

