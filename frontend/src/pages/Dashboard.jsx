import { useEffect, useState } from "react";
import { AlertTriangle, CalendarClock, CheckCircle2, LayoutDashboard, ShieldCheck, Users } from "lucide-react";
import { api } from "@/lib/api";

const CARDS = [
  { key: "clients", label: "Active clients", hint: "Companies in your portfolio", icon: Users, tone: "blue" },
  { key: "obligations", label: "Tracked obligations", hint: "Across every client", icon: LayoutDashboard, tone: "green" },
  { key: "overdue", label: "Overdue", hint: "Filings past their due date", icon: AlertTriangle, tone: "red" },
  { key: "due_soon", label: "Due within window", hint: "Marked due soon", icon: CalendarClock, tone: "amber" },
  { key: "completed", label: "Completed", hint: "Filed this cycle", icon: CheckCircle2, tone: "green" },
  { key: "team_utilisation", label: "Health index", hint: "Non-overdue coverage", icon: ShieldCheck, tone: "blue", suffix: "%" },
];

export default function Dashboard({ user, activeClient }) {
  const [stats, setStats] = useState(null);
  const [reminders, setReminders] = useState([]);

  useEffect(() => {
    api.get("/dashboard").then((r) => setStats(r.data)).catch(() => setStats({}));
    api.get("/reminders").then((r) => setReminders(r.data)).catch(() => setReminders([]));
  }, [activeClient?.id]);

  const noClients = stats && stats.clients === 0;

  if (noClients) {
    return (
      <div className="empty-hero" data-testid="dashboard-empty-hero">
        <div>
          <span className="eyebrow">GET STARTED IN 30 SECONDS</span>
          <h2>Welcome to ComplyEase, {user.name?.split(" ")[0]}</h2>
          <p>Your compliance operating system starts with one client company. Click the button below to open the tour, or jump straight into <b>Clients</b> and choose "Try with demo data" to see a fully populated workspace.</p>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="button primary" data-testid="dashboard-restart-tour" onClick={() => window.complyEaseRestartTour?.()}>Show me the tour</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <>
      <section className="metric-grid" data-testid="dashboard-metrics">
        {CARDS.map((c, i) => {
          const Icon = c.icon;
          const value = stats?.[c.key];
          return (
            <div className="metric" key={c.key}>
              <div className={`metric-icon ${c.tone}`}><Icon size={18} /></div>
              <div>
                <span>{c.label}</span>
                <strong data-testid={`metric-${c.key}-value`}>{value ?? 0}{c.suffix || ""}</strong>
                <small>{c.hint}</small>
              </div>
            </div>
          );
        })}
      </section>

      <div className="section-row">
        <div className="section-title"><h2>Upcoming across portfolio</h2><span className="count">{reminders.length} pending</span></div>
      </div>
      <section className="register" data-testid="portfolio-reminders">
        <div className="table-head">
          <span>OBLIGATION</span><span>CLIENT</span><span>DUE</span><span>STATUS</span><span>ASSIGNEE</span>
        </div>
        {reminders.slice(0, 12).map((r) => (
          <div className="table-row" key={r.id}>
            <div className="obligation">
              <span className={`risk-bar ${r.status === "Overdue" ? "danger" : r.status === "Due soon" ? "warning" : "success"}`} />
              <div><strong>{r.name}</strong><small>{r.form} · Section {r.section}</small></div>
            </div>
            <span className="owner">{r.client_name}</span>
            <span className="due"><b>{r.due || "—"}</b><small>{r.category}</small></span>
            <span><span className={`pill ${r.status === "Overdue" ? "danger" : r.status === "Due soon" ? "warning" : "success"}`}>{r.status}</span></span>
            <span className="owner">{r.assignee || "Unassigned"}</span>
          </div>
        ))}
        {!reminders.length && <div className="empty">No reminders yet — obligations will appear when you add clients.</div>}
      </section>
    </>
  );
}
