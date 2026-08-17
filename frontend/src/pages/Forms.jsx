import { useEffect, useState } from "react";
import { Download, FileText, Plus, Trash2, X } from "lucide-react";
import { api, API } from "@/lib/api";

const RELATIVES = [
  "Member of HUF of which Director is a member",
  "Spouse",
  "Father (including step Father)",
  "Mother (including step mother)",
  "Son (including step son)",
  "Son's wife",
  "Daughter (including step daughter)",
  "Daughter's husband",
  "Brother (including step brother)",
  "Sister (including step sister)",
];

function fyOptions() {
  const now = new Date();
  const year = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  return [-1, 0, 1].map((d) => {
    const s = year + d;
    return `${s}-${String((s + 1) % 100).padStart(2, "0")}`;
  });
}

export default function Forms({ activeClient, onToast }) {
  const [directors, setDirectors] = useState([]);
  const [editing, setEditing] = useState(null);
  const [fy, setFy] = useState(fyOptions()[1]);

  useEffect(() => {
    if (!activeClient) return;
    api.get(`/clients/${activeClient.id}/directors`).then((r) => setDirectors(r.data));
  }, [activeClient?.id]);

  const download = (form, dir) => {
    window.open(`${API}/clients/${activeClient.id}/forms/${form}/${dir.id}?fy=${fy}`, "_blank");
    onToast(`Generating ${form.toUpperCase()} for ${dir.name}`);
  };

  if (!activeClient) return <div className="empty">Select a client to generate MBP-1 / DIR-8.</div>;

  return (
    <div data-testid="forms-panel">
      <div className="import-hero">
        <FileText size={24} />
        <div>
          <h2>Generate MBP-1 &amp; DIR-8 for every director</h2>
          <p>MBP-1 (Section 184 · Rule 9(1)) — Director's notice of interest. DIR-8 (Section 164(2) · Rule 14(1)) — Director's non-disqualification. Fill each director's profile once, choose the FY, download the ready-to-sign Word document.</p>
        </div>
      </div>

      <div className="section-row" style={{ marginTop: 24 }}>
        <div className="section-title"><h2>Directors</h2><span className="count">{directors.length} listed</span></div>
        <div className="filters">
          <label className="fy-inline">
            Financial year
            <select data-testid="forms-fy-select" className="fy-select" value={fy} onChange={(e) => setFy(e.target.value)}>
              {fyOptions().map((f) => <option key={f} value={f}>FY {f}</option>)}
            </select>
          </label>
        </div>
      </div>

      <div className="forms-list" data-testid="forms-directors-list">
        {directors.map((d) => (
          <div className="form-director-card" key={d.id} data-testid={`form-director-${d.id}`}>
            <div className="form-director-head">
              <div>
                <strong>{d.name}</strong>
                <small>DIN {d.din || "—"} · {d.designation}</small>
                <small className="muted">
                  {d.father_name ? `S/o ${d.father_name}` : <em>Add father name</em>}
                  {" · "}
                  {d.address ? d.address.slice(0, 40) + (d.address.length > 40 ? "…" : "") : <em>Add residential address</em>}
                </small>
              </div>
              <div className="form-actions">
                <button data-testid={`edit-director-${d.id}`} className="button" onClick={() => setEditing(d)}>Edit profile</button>
                <button data-testid={`mbp1-${d.id}`} className="button primary" onClick={() => download("mbp1", d)}>
                  <Download size={13} /> MBP-1
                </button>
                <button data-testid={`dir8-${d.id}`} className="button primary" onClick={() => download("dir8", d)}>
                  <Download size={13} /> DIR-8
                </button>
              </div>
            </div>
            <div className="form-summary">
              <span data-testid={`interests-count-${d.id}`}>Interests: <b>{(d.interests || []).length}</b></span>
              <span data-testid={`directorships-count-${d.id}`}>Other directorships: <b>{(d.other_directorships || []).length}</b></span>
              <span data-testid={`relatives-count-${d.id}`}>Relatives listed: <b>{(d.relatives || []).length}</b></span>
              <span>Disqualification: <b>{d.has_disqualification ? "Yes" : "No"}</b></span>
            </div>
          </div>
        ))}
        {!directors.length && <div className="empty">No directors yet. Add them from the Master data tab or upload via Import.</div>}
      </div>

      {editing && (
        <DirectorEditor
          client={activeClient}
          director={editing}
          onClose={() => setEditing(null)}
          onSaved={(updated) => {
            setDirectors((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
            setEditing(null);
            onToast(`${updated.name} profile updated`);
          }}
        />
      )}
    </div>
  );
}

function DirectorEditor({ client, director, onClose, onSaved }) {
  const [form, setForm] = useState({
    father_name: director.father_name || "",
    address: director.address || "",
    has_disqualification: !!director.has_disqualification,
    interests: director.interests || [],
    other_directorships: director.other_directorships || [],
    relatives: director.relatives || [],
  });
  const [busy, setBusy] = useState(false);

  const setRel = (relation, name) => {
    const list = form.relatives.filter((r) => r.relation !== relation);
    if (name) list.push({ relation, name });
    setForm({ ...form, relatives: list });
  };
  const relValue = (relation) => (form.relatives.find((r) => r.relation === relation) || {}).name || "";

  const updateList = (key, index, patch) => {
    const list = [...form[key]];
    list[index] = { ...list[index], ...patch };
    setForm({ ...form, [key]: list });
  };
  const addRow = (key, blank) => setForm({ ...form, [key]: [...form[key], blank] });
  const removeRow = (key, index) => setForm({ ...form, [key]: form[key].filter((_, i) => i !== index) });

  const save = async () => {
    setBusy(true);
    try {
      const r = await api.patch(`/clients/${client.id}/directors/${director.id}/profile`, form);
      onSaved(r.data);
    } catch (err) {
      alert(err.response?.data?.detail || "Could not save");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} data-testid="director-editor-modal">
      <div className="modal wide" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose} data-testid="director-editor-close"><X size={16} /></button>
        <h2>Profile — {director.name}</h2>
        <p>The blanks below feed directly into MBP-1 &amp; DIR-8 for this director.</p>

        <div className="editor-grid">
          <label>Father's name
            <input data-testid="father-name-input" value={form.father_name} onChange={(e) => setForm({ ...form, father_name: e.target.value })} />
          </label>
          <label>Residential address
            <textarea data-testid="address-input" rows="2" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} />
          </label>
        </div>

        <div className="editor-section">
          <div className="editor-section-head">
            <strong>Interests in other bodies (MBP-1 Table I)</strong>
            <button className="button" onClick={() => addRow("interests", { entity_name: "", nature: "", shareholding: "", date: "" })} data-testid="add-interest-button"><Plus size={13} /> Add</button>
          </div>
          {form.interests.map((it, i) => (
            <div className="editor-row" key={i}>
              <input placeholder="Entity name" value={it.entity_name || ""} onChange={(e) => updateList("interests", i, { entity_name: e.target.value })} />
              <input placeholder="Nature" value={it.nature || ""} onChange={(e) => updateList("interests", i, { nature: e.target.value })} />
              <input placeholder="Shareholding" value={it.shareholding || ""} onChange={(e) => updateList("interests", i, { shareholding: e.target.value })} />
              <input placeholder="Date" type="date" value={it.date || ""} onChange={(e) => updateList("interests", i, { date: e.target.value })} />
              <button className="row-action" onClick={() => removeRow("interests", i)}><Trash2 size={13} /></button>
            </div>
          ))}
          {!form.interests.length && <div className="editor-empty">No interests recorded.</div>}
        </div>

        <div className="editor-section">
          <div className="editor-section-head">
            <strong>Other directorships in last 3 years (DIR-8)</strong>
            <button className="button" onClick={() => addRow("other_directorships", { name: "", appointment_date: "", cessation_date: "" })} data-testid="add-directorship-button"><Plus size={13} /> Add</button>
          </div>
          {form.other_directorships.map((it, i) => (
            <div className="editor-row" key={i}>
              <input placeholder="Company name" value={it.name || ""} onChange={(e) => updateList("other_directorships", i, { name: e.target.value })} />
              <input placeholder="Appointed" type="date" value={it.appointment_date || ""} onChange={(e) => updateList("other_directorships", i, { appointment_date: e.target.value })} />
              <input placeholder="Ceased" type="date" value={it.cessation_date || ""} onChange={(e) => updateList("other_directorships", i, { cessation_date: e.target.value })} />
              <button className="row-action" onClick={() => removeRow("other_directorships", i)}><Trash2 size={13} /></button>
            </div>
          ))}
          {!form.other_directorships.length && <div className="editor-empty">No other directorships recorded.</div>}
          <label className="checkbox">
            <input type="checkbox" data-testid="has-disqualification" checked={form.has_disqualification} onChange={(e) => setForm({ ...form, has_disqualification: e.target.checked })} />
            Director has incurred a disqualification under Section 164(2)
          </label>
        </div>

        <div className="editor-section">
          <strong>Relatives (MBP-1 Table III)</strong>
          <div className="relatives-grid">
            {RELATIVES.map((relation) => (
              <label key={relation}>
                <span>{relation}</span>
                <input value={relValue(relation)} onChange={(e) => setRel(relation, e.target.value)} placeholder="Full name" />
              </label>
            ))}
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
          <button className="button" onClick={onClose}>Cancel</button>
          <button className="button primary" data-testid="save-director-profile" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
        </div>
      </div>
    </div>
  );
}
