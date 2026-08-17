import { useEffect, useRef, useState } from "react";
import { Bell, X } from "lucide-react";
import { api } from "@/lib/api";

const BUCKET_LABEL = { overdue: "Overdue", t1: "Due today / tomorrow", t7: "Due within a week", t30: "Due within 30 days" };

export default function NotificationsBell({ onOpenClient }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ items: [], counts: { overdue: 0, t1: 0, t7: 0, t30: 0 } });
  const dropdownRef = useRef();

  const load = () => api.get("/notifications").then((r) => setData(r.data)).catch(() => {});
  useEffect(() => {
    load();
    const t = setInterval(load, 45000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => {
    const onClick = (e) => { if (dropdownRef.current && !dropdownRef.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const total = data.counts.overdue + data.counts.t1 + data.counts.t7 + data.counts.t30;

  const dismiss = async (id) => {
    await api.post(`/notifications/${id}/dismiss`);
    load();
  };

  return (
    <div className="notifications-wrap" ref={dropdownRef}>
      <button data-testid="notifications-bell" className="notif-btn" onClick={() => setOpen(!open)}>
        <Bell size={17} />
        {total > 0 && <span className="notif-dot" data-testid="notifications-count">{total}</span>}
      </button>
      {open && (
        <div className="notif-panel" data-testid="notifications-panel">
          <div className="notif-header">
            <strong>Reminders</strong>
            <div className="notif-counts">
              <span className="pill danger" data-testid="notif-count-overdue">{data.counts.overdue} overdue</span>
              <span className="pill warning">{data.counts.t7} in a week</span>
              <span className="pill neutral">{data.counts.t30} in a month</span>
            </div>
          </div>
          <div className="notif-list">
            {data.items.length === 0 && <div className="empty">All clear. No pending filings within the next 30 days.</div>}
            {data.items.map((n) => (
              <div className={`notif-item ${n.tone}`} key={n.id} data-testid={`notif-item-${n.id}`}>
                <div>
                  <strong>{n.form} · {n.name}</strong>
                  <small>{n.client_name} · Due {n.due} ({n.days < 0 ? `${-n.days}d late` : `${n.days}d away`}) · {n.assignee || "Unassigned"}</small>
                </div>
                <button data-testid={`notif-jump-${n.id}`} className="row-action" onClick={() => { onOpenClient(n.client_id); setOpen(false); }}>Open</button>
                <button data-testid={`notif-dismiss-${n.id}`} className="row-action muted" onClick={() => dismiss(n.id)}><X size={13} /></button>
              </div>
            ))}
          </div>
          <div className="notif-footer">{BUCKET_LABEL[data.items[0]?.bucket] || "T-30 window"}</div>
        </div>
      )}
    </div>
  );
}
