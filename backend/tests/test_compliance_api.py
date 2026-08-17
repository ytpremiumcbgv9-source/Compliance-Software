import os, io, requests, pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")

def test_clients_seed_and_obligations():
    r=requests.get(f"{BASE_URL}/api/clients", timeout=20); assert r.status_code==200
    clients=r.json(); assert len(clients)>=3 and all(c.get("id") for c in clients)
    o=requests.get(f"{BASE_URL}/api/clients/{clients[0]['id']}/obligations", timeout=20); assert o.status_code==200
    rows=o.json(); assert len(rows)>=5 and all(row.get("client_id")==clients[0]["id"] for row in rows)

def test_status_patch_persists():
    c=requests.get(f"{BASE_URL}/api/clients", timeout=20).json()[0]
    rows=requests.get(f"{BASE_URL}/api/clients/{c['id']}/obligations", timeout=20).json(); row=rows[0]
    new="Completed" if row["status"]!="Completed" else "On track"
    r=requests.patch(f"{BASE_URL}/api/obligations/{row['id']}", json={"status":new}, timeout=20); assert r.status_code==200; assert r.json()["status"]==new
    again=requests.get(f"{BASE_URL}/api/clients/{c['id']}/obligations", timeout=20).json(); assert next(x for x in again if x["id"]==row["id"])["status"]==new

def test_create_client_and_upload_evidence():
    payload={"name":"TEST_Review Client","code":"TEST-999","sector":"Private company","state":"Maharashtra"}
    r=requests.post(f"{BASE_URL}/api/clients", json=payload, timeout=20); assert r.status_code==200; c=r.json(); assert c["name"]==payload["name"]
    u=requests.post(f"{BASE_URL}/api/clients/{c['id']}/evidence", files={"file":("test.txt", io.BytesIO(b"evidence"),"text/plain")}, timeout=20); assert u.status_code==200; assert u.json()["filename"]=="test.txt"
