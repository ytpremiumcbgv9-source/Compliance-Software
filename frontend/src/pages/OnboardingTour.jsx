import { useEffect, useState } from "react";
import { ArrowRight, Sparkles, X } from "lucide-react";
import { api } from "@/lib/api";

const STEPS = [
  {
    id: "welcome",
    title: "Welcome to ComplyEase 👋",
    body: "This 40-second tour will show you how a PCS practice tracks every client's statutory calendar without opening a spreadsheet.",
    cta: "Start tour",
  },
  {
    id: "clients",
    title: "1 · Client workspaces",
    body: "Every company you advise gets its own isolated workspace. Try the demo — one click and you'll see a fully populated company with directors, shareholders, financials and a live compliance calendar.",
    target: '[data-testid="nav-clients-button"]',
    highlight: "clients",
    cta: "Try with demo data",
    action: "demo",
  },
  {
    id: "register",
    title: "2 · Statutory calendar in one click",
    body: "Open the Register and hit \"Generate FY\" — you'll get MGT-7, AOC-4, DIR-3 KYC, ADT-1, DPT-3, MSME-1, four board meetings and 6 more, each with the correct due date.",
    target: '[data-testid="nav-register-button"]',
    highlight: "register",
    cta: "Show me the register",
  },
  {
    id: "makerchecker",
    title: "3 · Team-safe filing (maker-checker)",
    body: "Expand any row. An article assistant clicks \"Submit for review\"; the partner then Approves or sends it back. Every action is written to an immutable audit trail.",
    highlight: "register",
    cta: "Got it",
  },
  {
    id: "registers",
    title: "4 · Members, Charges & Resolutions",
    body: "Statutory Registers keeps MGT-1, MBP-1, CHG-7, MBP-4 up-to-date and exports each as a CSV with the company header — ready to hand to clients.",
    target: '[data-testid="nav-registers-button"]',
    highlight: "registers",
    cta: "Next",
  },
  {
    id: "imports",
    title: "5 · Bring your Excel",
    body: "Have a directors list or financials in a workbook already? Drop it in — ComplyEase reads every tab, guesses the column mapping, and one click writes real records.",
    target: '[data-testid="nav-imports-button"]',
    highlight: "imports",
    cta: "Next",
  },
  {
    id: "notifications",
    title: "6 · Never miss a filing",
    body: "The bell in the top bar shows every obligation due in 30 days, 7 days, tomorrow, and everything overdue — grouped, dismissible, and jump-to-client.",
    target: '[data-testid="notifications-bell"]',
    highlight: "notifications",
    cta: "Done — take me in",
  },
];

const LOCAL_KEY = "complyease.tour.completed.v1";

export default function OnboardingTour({ user, onDemo, onNavigate }) {
  const [step, setStep] = useState(0);
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!user) return;
    const done = localStorage.getItem(LOCAL_KEY);
    if (!done) setTimeout(() => setVisible(true), 400);
  }, [user]);

  useEffect(() => {
    if (!visible) return;
    const s = STEPS[step];
    if (!s?.target) { setPos(null); return; }
    const el = document.querySelector(s.target);
    if (!el) { setPos(null); return; }
    const rect = el.getBoundingClientRect();
    setPos({ top: rect.top, left: rect.left, width: rect.width, height: rect.height });
  }, [step, visible]);

  const close = () => {
    localStorage.setItem(LOCAL_KEY, "1");
    setVisible(false);
  };

  const next = async () => {
    const s = STEPS[step];
    if (s.action === "demo") {
      setBusy(true);
      try {
        const r = await api.post("/clients/demo");
        onDemo?.(r.data.client);
      } catch (err) {
        // continue even if demo fails
      } finally {
        setBusy(false);
      }
    }
    if (s.highlight) onNavigate?.(s.highlight);
    if (step === STEPS.length - 1) close();
    else setStep(step + 1);
  };

  const restart = () => {
    localStorage.removeItem(LOCAL_KEY);
    setStep(0);
    setVisible(true);
  };

  // Expose restart handler on window for the "Help" button
  useEffect(() => { window.complyEaseRestartTour = restart; }, []);

  if (!visible) return null;
  const s = STEPS[step];

  return (
    <>
      <div className="tour-backdrop" data-testid="tour-backdrop" onClick={close} />
      {pos && (
        <div
          className="tour-spotlight"
          style={{ top: pos.top - 6, left: pos.left - 6, width: pos.width + 12, height: pos.height + 12 }}
        />
      )}
      <div className="tour-card" data-testid={`tour-step-${s.id}`}>
        <button className="tour-close" data-testid="tour-skip-button" onClick={close}><X size={15} /></button>
        <div className="tour-badge"><Sparkles size={13} /> Step {step + 1} of {STEPS.length}</div>
        <h3>{s.title}</h3>
        <p>{s.body}</p>
        <div className="tour-actions">
          {step > 0 && <button className="text-button" data-testid="tour-back-button" onClick={() => setStep(step - 1)}>← Back</button>}
          <button className="button primary" data-testid="tour-next-button" onClick={next} disabled={busy}>
            {busy ? "Loading demo…" : s.cta} <ArrowRight size={14} />
          </button>
        </div>
      </div>
    </>
  );
}
