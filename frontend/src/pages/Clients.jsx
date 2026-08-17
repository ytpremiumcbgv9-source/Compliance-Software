import { useState } from "react";
import { api } from "@/lib/api";

export default function Clients({ clients, setActive, onCreated, user }) {
  const [form, setForm] = useState({});
  const [message, setMessage] = useState("");

  const create = async (e) => {
    e.preventDefault();
    setMessage("");
    try {
      const r = await api.post("/clients", form);
      onCreated(r.data);
      setActive(r.data);
      setForm({});
    } catch (err) {
      setMessage(err.response?.data?.detail || "Could not create client");
    }
  };

  return (
    <>
      <div className="section-row">
        <div className="section-title"><h2>Client workspaces</h2>
          <span className="count">{clients.length} of {user.client_limit} allowed</span></div>
      </div>
      <div className="lower-grid">
        <form data-testid="client-create-form" className="modal-inline" onSubmit={create}>
          <div className="eyebrow">NEW CLIENT</div>
          <h3>Start a company workspace</h3>
          <label>Company name<input data-testid="client-name-input" required value={form.name || ""} onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
          <label>Client code<input data-testid="client-code-input" required value={form.code || ""} onChange={(e) => setForm({ ...form, code: e.target.value })} /></label>
          <label>CIN (optional)<input data-testid="client-cin-input" value={form.cin || ""} onChange={(e) => setForm({ ...form, cin: e.target.value })} /></label>
          <label>Registered state<input data-testid="client-state-input" value={form.state || ""} onChange={(e) => setForm({ ...form, state: e.target.value })} /></label>
          <button data-testid="save-client-button" className="button primary">Create workspace</button>
          {message && <small data-testid="client-create-error" className="form-error">{message}</small>}
        </form>
        <div className="client-grid" data-testid="client-grid">
          {clients.map((c) => (
            <button data-testid={`client-${c.id}-card`} className="client-card" onClick={() => setActive(c)} key={c.id}>
              <span className="client-logo">{c.name.slice(0, 2).toUpperCase()}</span>
              <div>
                <strong>{c.name}</strong>
                <small>{c.code} · {c.sector}</small>
                <small>{c.obligations_count || 0} obligations · {c.overdue_count || 0} overdue</small>
              </div>
              <b>{c.health}%</b>
            </button>
          ))}
          {!clients.length && <div className="empty">No clients yet. Create one on the left.</div>}
        </div>
      </div>
    </>
  );
}
