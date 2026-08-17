import { useState } from "react";
import { api } from "@/lib/api";

export default function Settings({ user, onProfileUpdate, onToast }) {
  const [profile, setProfile] = useState({ name: user.name, practice_name: user.practice_name });
  const [pwd, setPwd] = useState({ current_password: "", new_password: "", confirm: "" });
  const [busyProfile, setBusyProfile] = useState(false);
  const [busyPwd, setBusyPwd] = useState(false);

  const saveProfile = async (e) => {
    e.preventDefault();
    setBusyProfile(true);
    try {
      const r = await api.patch("/auth/profile", profile);
      onProfileUpdate(r.data);
      onToast("Profile updated");
    } catch (err) {
      onToast(err.response?.data?.detail || "Could not update profile");
    } finally {
      setBusyProfile(false);
    }
  };

  const savePwd = async (e) => {
    e.preventDefault();
    if (pwd.new_password !== pwd.confirm) { onToast("Passwords do not match"); return; }
    if (pwd.new_password.length < 8) { onToast("New password must be at least 8 characters"); return; }
    setBusyPwd(true);
    try {
      await api.post("/auth/change-password", { current_password: pwd.current_password, new_password: pwd.new_password });
      onToast("Password updated");
      setPwd({ current_password: "", new_password: "", confirm: "" });
    } catch (err) {
      onToast(err.response?.data?.detail || "Could not change password");
    } finally {
      setBusyPwd(false);
    }
  };

  return (
    <div data-testid="settings-panel" style={{ display: "grid", gap: 24 }}>
      <form className="profile-card" onSubmit={saveProfile} data-testid="profile-form">
        <div className="eyebrow">ACCOUNT</div>
        <h3>Your profile</h3>
        <p>Displayed in the register, audit trail and team panel.</p>
        <label>Full name
          <input data-testid="profile-name-input" required value={profile.name || ""} onChange={(e) => setProfile({ ...profile, name: e.target.value })} />
        </label>
        <label>Practice name
          <input data-testid="profile-practice-input" required value={profile.practice_name || ""} onChange={(e) => setProfile({ ...profile, practice_name: e.target.value })} />
        </label>
        <dl className="profile-detail">
          <dt>Email</dt><dd data-testid="profile-email">{user.email}</dd>
          <dt>Role</dt><dd>{user.role === "owner" ? "Master owner" : "Member"}</dd>
          <dt>Status</dt><dd>{user.status}</dd>
          <dt>Client limit</dt><dd>{user.client_limit}</dd>
        </dl>
        <button className="button primary" data-testid="save-profile-button" disabled={busyProfile}>
          {busyProfile ? "Saving…" : "Save profile"}
        </button>
      </form>

      <form className="profile-card" onSubmit={savePwd} data-testid="password-form">
        <div className="eyebrow">SECURITY</div>
        <h3>Change password</h3>
        <p>Passwords must be at least 8 characters. You will stay signed in on this device.</p>
        <label>Current password
          <input data-testid="current-password-input" type="password" required value={pwd.current_password} onChange={(e) => setPwd({ ...pwd, current_password: e.target.value })} />
        </label>
        <label>New password
          <input data-testid="new-password-input" type="password" required minLength="8" value={pwd.new_password} onChange={(e) => setPwd({ ...pwd, new_password: e.target.value })} />
        </label>
        <label>Confirm new password
          <input data-testid="confirm-password-input" type="password" required value={pwd.confirm} onChange={(e) => setPwd({ ...pwd, confirm: e.target.value })} />
        </label>
        <button className="button primary" data-testid="save-password-button" disabled={busyPwd}>
          {busyPwd ? "Updating…" : "Update password"}
        </button>
      </form>
    </div>
  );
}
