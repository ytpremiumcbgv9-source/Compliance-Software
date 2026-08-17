import { useEffect, useState } from "react";
import {
  Activity, Building2, CalendarDays, CheckCircle2, ClipboardCheck,
  FileSpreadsheet, History, LayoutDashboard, LogOut, Plus, ShieldCheck, UserSquare2, Users,
} from "lucide-react";

import { api, cx } from "@/lib/api";
import AuthScreen from "@/pages/AuthScreen";
import Dashboard from "@/pages/Dashboard";
import Register from "@/pages/Register";
import Clients from "@/pages/Clients";
import ImportWizard from "@/pages/ImportWizard";
import MasterData from "@/pages/MasterData";
import OwnerPanel from "@/pages/Owner";
import AuditTrail from "@/pages/AuditTrail";

import "@/App.css";

const TABS_BASE = [
  ["dashboard", "Overview", LayoutDashboard],
  ["clients", "Clients", Building2],
  ["register", "Register", ClipboardCheck],
  ["master", "Master data", UserSquare2],
  ["imports", "Import data", FileSpreadsheet],
  ["audit", "Audit trail", History],
];

export default function App() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [clients, setClients] = useState([]);
  const [active, setActive] = useState(null);
  const [tab, setTab] = useState("dashboard");
  const [toast, setToast] = useState("");
  const [masterRefresh, setMasterRefresh] = useState(0);

  useEffect(() => {
    api.get("/auth/me").then((r) => setUser(r.data)).catch(() => {}).finally(() => setChecking(false));
  }, []);

  const refreshClients = () =>
    api.get("/clients").then((r) => {
      setClients(r.data);
      if (!active && r.data.length) setActive(r.data[0]);
    }).catch(() => {});

  useEffect(() => { if (user) refreshClients(); /* eslint-disable-next-line */ }, [user]);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(""), 2600);
      return () => clearTimeout(t);
    }
  }, [toast]);

  if (checking) return <div className="loading-screen">Loading workspace…</div>;
  if (!user) return <AuthScreen onAuth={setUser} />;

  const logout = async () => {
    await api.post("/auth/logout");
    setUser(null);
    setClients([]);
    setActive(null);
  };

  const tabs = [...TABS_BASE, ...(user.role === "owner" ? [["approvals", "Team", Users]] : [])];

  const tabTitle = {
    dashboard: `Good morning, ${user.name?.split(" ")[0]}`,
    clients: "Client workspaces",
    register: "Compliance register",
    master: "Master data",
    imports: "Import from Excel",
    audit: "Audit trail",
    approvals: "Team & approvals",
  }[tab];

  const bumpMaster = () => setMasterRefresh((v) => v + 1);

  const notify = (msg) => setToast(msg);

  return (
    <div className="shell">
      <aside className="rail">
        <div className="brand"><span className="brand-mark"><ShieldCheck size={18} /></span><span>comply<span>ease</span></span></div>
        <div className="workspace-label">PCS WORKSPACE</div>
        <nav>
          {tabs.map(([id, label, Icon]) => (
            <button data-testid={`nav-${id}-button`} className={cx("nav-item", tab === id && "active")} onClick={() => setTab(id)} key={id}>
              <Icon size={17} />{label}
            </button>
          ))}
        </nav>
        <div className="rail-bottom">
          <div className="sync">
            <span className="dot" />
            {user.role === "owner" ? "MASTER OWNER" : "APPROVED MEMBER"}
            <small>{user.practice_name}</small>
          </div>
          <button data-testid="logout-button" className="nav-item" onClick={logout}><LogOut size={17} />Sign out</button>
        </div>
      </aside>

      <main className="main">
        <header className="topbar">
          <div className="crumb">
            <span>{user.practice_name}</span>
            <span className="muted">⌄</span>
            <div className="client-switch">
              <Building2 size={15} />
              <select data-testid="client-switcher" value={active?.id || ""} onChange={(e) => setActive(clients.find((c) => c.id === e.target.value))}>
                <option value="" disabled>Select client…</option>
                {clients.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
              </select>
            </div>
          </div>
          <div className="top-actions">
            <span className="date-chip"><CalendarDays size={15} /> {new Date().toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })}</span>
            <div className="avatar" data-testid="user-avatar">{user.name?.slice(0, 2).toUpperCase()}</div>
          </div>
        </header>

        <div className="content">
          <div className="page-head">
            <div>
              <div className="eyebrow">
                {user.role === "owner" ? "MASTER OWNER" : "APPROVED MEMBER"} / {active?.code || "SETUP"}
              </div>
              <h1 data-testid="page-title">{tabTitle}</h1>
              <p data-testid="active-client-name">
                {active?.name || "Create your first client workspace"}
                <span className="muted"> · {clients.length} of {user.client_limit} clients</span>
              </p>
            </div>
            <div className="head-actions">
              <button data-testid="add-client-button" className="button primary" onClick={() => setTab("clients")}><Plus size={16} /> Add client</button>
            </div>
          </div>

          {tab === "dashboard" && <Dashboard user={user} activeClient={active} />}
          {tab === "clients" && (
            <Clients
              clients={clients} setActive={setActive}
              onCreated={() => refreshClients()} user={user}
            />
          )}
          {tab === "register" && (
            active
              ? <Register activeClient={active} onToast={notify} />
              : <div className="empty">Select or create a client to open the register.</div>
          )}
          {tab === "master" && <MasterData activeClient={active} onToast={notify} refreshToken={masterRefresh} />}
          {tab === "imports" && (
            active
              ? <ImportWizard activeClient={active} onToast={notify} refreshMasterCounts={bumpMaster} />
              : <div className="empty">Select or create a client before importing source data.</div>
          )}
          {tab === "audit" && <AuditTrail activeClient={active} />}
          {tab === "approvals" && <OwnerPanel onToast={notify} />}
        </div>

        {toast && <div data-testid="toast-message" className="toast"><CheckCircle2 size={17} />{toast}</div>}
      </main>
    </div>
  );
}
