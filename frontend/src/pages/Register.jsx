import { useEffect, useState } from "react";
import { ArrowUpRight, Search } from "lucide-react";
import { api } from "@/lib/api";

const STATUSES = ["On track", "Due soon", "Under review", "Overdue", "Completed"];

export default function Register({ activeClient, onToast }) {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    if (!activeClient) return;
    api.get(`/clients/${activeClient.id}/obligations`).then((r) => setItems(r.data));
  }, [activeClient?.id]);

  const patch = async (id, changes) => {
    const r = await api.patch(`/obligations/${id}`, changes);
    setItems((v) => v.map((x) => (x.id === id ? r.data : x)));
    onToast("Register updated");
  };

  const shown = items.filter((x) => (x.name + x.form + (x.assignee || "")).toLowerCase().includes(query.toLowerCase()));

  return (
    <>
      <div className="section-row">
        <div className="section-title"><h2>Compliance register</h2><span className="count">{items.length} tracked</span></div>
        <div className="filters">
          <div className="search"><Search size={15} /><input data-testid="obligation-search-input" placeholder="Search obligations" onChange={(e) => setQuery(e.target.value)} /></div>
        </div>
      </div>

      <section className="register" data-testid="obligation-table">
        <div className="table-head">
          <span>OBLIGATION</span><span>ASSIGNEE</span><span>DUE</span><span>STATUS</span><span>ACTION</span>
        </div>
        {shown.map((x) => (
          <div className="table-row-wrap" key={x.id}>
            <div className="table-row">
              <div className="obligation">
                <span className={`risk-bar ${x.status === "Overdue" ? "danger" : x.status === "Due soon" ? "warning" : "success"}`} />
                <div><strong data-testid={`obligation-${x.id}-name`}>{x.name}</strong><small>{x.form} · Section {x.section}</small></div>
              </div>
              <span className="owner">
                <input data-testid={`obligation-${x.id}-assignee`} defaultValue={x.assignee || ""} placeholder="Assignee"
                  onBlur={(e) => e.target.value !== (x.assignee || "") && patch(x.id, { assignee: e.target.value })} />
              </span>
              <span className="due"><b>{x.due || "—"}</b><small>{x.category}</small></span>
              <span>
                <select data-testid={`obligation-${x.id}-status`} className={`status-select ${x.status === "Overdue" ? "danger" : x.status === "Due soon" ? "warning" : "success"}`}
                  value={x.status} onChange={(e) => patch(x.id, { status: e.target.value })}>
                  {STATUSES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </span>
              <button data-testid={`obligation-${x.id}-expand`} className="row-action" onClick={() => setExpanded(expanded === x.id ? null : x.id)}>
                {expanded === x.id ? "Close" : "Open"} <ArrowUpRight size={14} />
              </button>
            </div>
            {expanded === x.id && (
              <div className="obligation-detail" data-testid={`obligation-${x.id}-detail`}>
                <div>
                  <label>Filed date<input data-testid={`obligation-${x.id}-filed`} type="date" defaultValue={x.filed_date || ""} onBlur={(e) => patch(x.id, { filed_date: e.target.value })} /></label>
                  <label>SRN / Ack no.<input data-testid={`obligation-${x.id}-srn`} defaultValue={x.srn || ""} onBlur={(e) => e.target.value !== (x.srn || "") && patch(x.id, { srn: e.target.value })} /></label>
                </div>
                <label>Working remarks<textarea data-testid={`obligation-${x.id}-remarks`} rows="3" defaultValue={x.remarks || ""} onBlur={(e) => e.target.value !== (x.remarks || "") && patch(x.id, { remarks: e.target.value })} /></label>
                <p className="obligation-description">{x.description}</p>
              </div>
            )}
          </div>
        ))}
        {!shown.length && <div className="empty">No obligations match your search.</div>}
      </section>
    </>
  );
}
