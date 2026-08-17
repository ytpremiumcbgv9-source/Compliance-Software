import { useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/api";

export default function Clients({ clients, setActive, onCreated, user }) {
  const [form, setForm] = useState({});
  const [message, setMessage] = useState("");
  const [demoBusy, setDemoBusy] = useState(false);

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

  const createDemo = async () => {
    setDemoBusy(true);
    try {
      const r = await api.post("/clients/demo");
      onCreated(r.data.client);
      setActive(r.data.client);
    } catch (err) {
      setMessage(err.response?.data?.detail || "Could not create demo client");
    } finally {
      setDemoBusy(false);
    }
  };

  const empty = clients.length === 0;

  return (
    <>
      <div className="section-row">
        <div className="section-title"><h2>Client workspaces</h2>
          <span className="count">{clients.length} of {user.client_limit} allowed</span></div>
        {empty && (
          <button data-testid="create-demo-button" className="button" onClick={createDemo} disabled={demoBusy}>
            <Sparkles size={14} /> {demoBusy ? "Creating…" : "Try with demo data"}
          </button>
        )}
      </div>

      {empty && (
        <div className="empty-hero" data-testid="clients-empty-hero">
          <div>
            <span className="eyebrow">FIRST STEP</span>
            <h2>Start with a company, or try a demo</h2>
            <p>Create a real client on the right — or click <b>Try with demo data</b> to spin up "Sunrise Innovations" with 3 directors, 3 shareholders, financials and a full FY compliance calendar in seconds.</p>
            <button className="button primary" onClick={createDemo} disabled={demoBusy} data-testid="empty-hero-demo-button">
              <Sparkles size={15} /> {demoBusy ? "Loading demo…" : "Load demo company"}
            </button>
          </div>
        </div>
      )}

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
                <strong>{c.name}{c.is_demo && <span className="demo-pill">DEMO</span>}</strong>
                <small>{c.code} · {c.sector}</small>
                <small>{c.obligations_count || 0} obligations · {c.overdue_count || 0} overdue</small>
              </div>
              <b>{c.health}%</b>
            </button>
          ))}
          {!clients.length && <div className="empty">No clients yet. Create one on the left, or use the demo above.</div>}
        </div>
      </div>
    </>
  );
}
