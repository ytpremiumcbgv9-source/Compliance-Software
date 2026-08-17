import { useEffect, useState } from "react";
import { Users } from "lucide-react";
import { api } from "@/lib/api";

export default function OwnerPanel({ onToast }) {
  const [requests, setRequests] = useState([]);
  const [users, setUsers] = useState([]);
  const [tab, setTab] = useState("requests");

  const load = async () => {
    try { setRequests((await api.get("/owner/requests")).data); } catch {}
    try { setUsers((await api.get("/owner/users")).data); } catch {}
  };
  useEffect(() => { load(); }, []);

  const act = async (id, approved) => {
    await api.patch(`/owner/requests/${id}`, { approved, client_limit: 5 });
    onToast(approved ? "Account approved" : "Request declined");
    load();
  };

  const updateLimit = async (id, client_limit) => {
    await api.patch(`/owner/users/${id}/limit`, { client_limit: Math.max(1, Number(client_limit) || 1) });
    onToast("Client limit updated");
    load();
  };

  const toggleStatus = async (user) => {
    const status = user.status === "suspended" ? "approved" : "suspended";
    await api.patch(`/owner/users/${user.id}/status`, { status });
    onToast(`User ${status}`);
    load();
  };

  return (
    <div data-testid="owner-panel">
      <div className="master-tabs">
        <button data-testid="owner-tab-requests" className={`master-tab ${tab === "requests" ? "active" : ""}`} onClick={() => setTab("requests")}>
          Requests <b>{requests.length}</b>
        </button>
        <button data-testid="owner-tab-users" className={`master-tab ${tab === "users" ? "active" : ""}`} onClick={() => setTab("users")}>
          Team <b>{users.length}</b>
        </button>
      </div>

      {tab === "requests" ? (
        <div className="calendar-list" data-testid="requests-list">
          {requests.map((r) => (
            <div className="calendar-item" key={r.id}>
              <div className="calendar-day"><Users size={20} /></div>
              <div>
                <strong>{r.name}</strong>
                <small>{r.email} · {r.practice_name}</small>
              </div>
              <button data-testid={`approve-${r.id}-button`} className="button primary" onClick={() => act(r.id, true)}>Approve</button>
              <button data-testid={`reject-${r.id}-button`} className="button secondary" onClick={() => act(r.id, false)}>Decline</button>
            </div>
          ))}
          {!requests.length && <div className="empty">No pending requests. New PCS signups will appear here.</div>}
        </div>
      ) : (
        <div className="calendar-list" data-testid="users-list">
          {users.map((u) => (
            <div className="calendar-item" key={u.id}>
              <div className="calendar-day"><Users size={20} /></div>
              <div>
                <strong>{u.name}</strong>
                <small>{u.email} · {u.practice_name} · {u.clients_used} of {u.client_limit} clients used</small>
              </div>
              <label className="limit-editor">
                Client limit
                <input data-testid={`limit-${u.id}-input`} type="number" min="1" defaultValue={u.client_limit}
                  onBlur={(e) => Number(e.target.value) !== u.client_limit && updateLimit(u.id, e.target.value)} />
              </label>
              <button data-testid={`status-${u.id}-button`} className={`button ${u.status === "suspended" ? "primary" : "secondary"}`} onClick={() => toggleStatus(u)}>
                {u.status === "suspended" ? "Reactivate" : "Suspend"}
              </button>
              <span className={`pill ${u.status === "approved" ? "success" : u.status === "suspended" ? "danger" : "neutral"}`}>{u.status}</span>
            </div>
          ))}
          {!users.length && <div className="empty">Once you approve members they will appear here.</div>}
        </div>
      )}
    </div>
  );
}
