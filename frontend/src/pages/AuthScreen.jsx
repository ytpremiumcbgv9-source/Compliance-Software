import { useState } from "react";
import { ArrowUpRight, CheckCircle2, ShieldCheck } from "lucide-react";
import { api } from "@/lib/api";

export default function AuthScreen({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      const path = mode === "login" ? "/auth/login" : "/auth/signup";
      const r = await api.post(path, form);
      setMessage(r.data.message || "Welcome back");
      if (mode === "login") onAuth(r.data);
      else setMode("login");
    } catch (err) {
      setMessage(err.response?.data?.detail || "Please check your details and try again");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-art">
        <div className="brand"><span className="brand-mark"><ShieldCheck size={18} /></span><span>comply<span>ease</span></span></div>
        <div>
          <div className="eyebrow">COMPLIANCE OPERATING SYSTEM</div>
          <h1>Make every client deadline feel under control.</h1>
          <p>One workspace for the companies you advise, with source-data imports that turn your Excel files into ready-to-track compliance records.</p>
        </div>
        <div className="auth-proof"><CheckCircle2 size={17} /> Built for PCS practices managing multiple companies</div>
      </div>
      <form data-testid="auth-form" className="auth-form" onSubmit={submit}>
        <div className="eyebrow">{mode === "login" ? "WELCOME BACK" : "REQUEST ACCESS"}</div>
        <h2>{mode === "login" ? "Sign in to your workspace" : "Ask for a workspace"}</h2>
        <p>{mode === "login"
          ? "Use the account approved by your practice owner."
          : "Your first account becomes the master owner. Future requests wait for approval."}</p>
        {mode !== "login" && (
          <>
            <label>Your name<input data-testid="signup-name-input" required onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label>Practice name<input data-testid="signup-practice-input" required onChange={(e) => setForm({ ...form, practice_name: e.target.value })} /></label>
          </>
        )}
        <label>Email<input data-testid="auth-email-input" type="email" required onChange={(e) => setForm({ ...form, email: e.target.value })} /></label>
        <label>Password<input data-testid="auth-password-input" type="password" required minLength="8" onChange={(e) => setForm({ ...form, password: e.target.value })} /></label>
        {message && <div data-testid="auth-message" className="auth-message">{message}</div>}
        <button data-testid="auth-submit-button" className="button primary" disabled={busy}>
          {busy ? "Working…" : (mode === "login" ? "Sign in" : "Send approval request")} <ArrowUpRight size={16} />
        </button>
        <button data-testid="auth-mode-button" type="button" className="text-button auth-toggle" onClick={() => { setMode(mode === "login" ? "signup" : "login"); setMessage(""); }}>
          {mode === "login" ? "Need access? Send a signup request" : "Already approved? Sign in"}
        </button>
      </form>
    </div>
  );
}
