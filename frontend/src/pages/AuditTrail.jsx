import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function AuditTrail({ activeClient }) {
  const [rows, setRows] = useState([]);

  useEffect(() => {
    if (!activeClient) return;
    api.get(`/clients/${activeClient.id}/audit-log`).then((r) => setRows(r.data)).catch(() => setRows([]));
  }, [activeClient?.id]);

  if (!activeClient) return <div className="empty">Select a client to view its audit trail.</div>;

  return (
    <div data-testid="audit-panel">
      <div className="section-row">
        <div className="section-title"><h2>Audit trail</h2><span className="count">{rows.length} events</span></div>
      </div>
      <section className="register">
        <div className="table-head">
          <span>WHEN</span><span>WHO</span><span>ACTION</span><span>DETAIL</span><span>ENTITY</span>
        </div>
        {rows.map((r) => (
          <div className="table-row" key={r.id}>
            <span className="due"><b>{new Date(r.created_at).toLocaleDateString()}</b><small>{new Date(r.created_at).toLocaleTimeString()}</small></span>
            <span className="owner">{r.actor_name}</span>
            <span><span className="pill neutral">{r.action}</span></span>
            <span className="owner" data-testid={`audit-${r.id}-detail`}>{r.detail}</span>
            <span className="owner">{r.entity || "—"}</span>
          </div>
        ))}
        {!rows.length && <div className="empty">No events yet. Actions like status changes, imports and evidence uploads will land here.</div>}
      </section>
    </div>
  );
}
