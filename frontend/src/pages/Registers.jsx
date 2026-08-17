import { useEffect, useState } from "react";
import { Download, FileText, Trash2 } from "lucide-react";
import { api, API } from "@/lib/api";

const SPECS = {
  shareholders: {
    label: "Members",
    fields: [
      { key: "name", label: "Name", required: true },
      { key: "folio_no", label: "Folio no." },
      { key: "pan", label: "PAN" },
      { key: "shares_held", label: "Shares held", type: "number" },
      { key: "share_class", label: "Class" },
      { key: "date_of_holding", label: "Held since", type: "date" },
      { key: "email", label: "Email" },
    ],
  },
  charges: {
    label: "Charges",
    fields: [
      { key: "charge_id", label: "Charge ID" },
      { key: "creation_date", label: "Created on", type: "date" },
      { key: "amount", label: "Amount", type: "number" },
      { key: "holder", label: "Charge holder", required: true },
      { key: "description", label: "Description" },
      { key: "status", label: "Status" },
      { key: "modification_date", label: "Modified on", type: "date" },
      { key: "satisfaction_date", label: "Satisfied on", type: "date" },
    ],
  },
  resolutions: {
    label: "Resolutions",
    fields: [
      { key: "number", label: "Number", required: true },
      { key: "passed_on", label: "Passed on", type: "date" },
      { key: "resolution_type", label: "Type" },
      { key: "subject", label: "Subject", required: true },
      { key: "body", label: "Body" },
      { key: "filing_form", label: "Filed form" },
    ],
  },
  contracts: {
    label: "Contracts",
    fields: [
      { key: "counterparty", label: "Counterparty", required: true },
      { key: "relationship", label: "Relationship" },
      { key: "nature", label: "Nature" },
      { key: "value", label: "Value", type: "number" },
      { key: "start_date", label: "Start", type: "date" },
      { key: "end_date", label: "End", type: "date" },
      { key: "approval_reference", label: "Approval ref." },
    ],
  },
};

export default function Registers({ activeClient, onToast }) {
  const [registers, setRegisters] = useState([]);
  const [tab, setTab] = useState("shareholders");
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState({});

  const load = async () => {
    if (!activeClient) return;
    try { setRegisters((await api.get(`/clients/${activeClient.id}/registers`)).data); } catch {}
    if (SPECS[tab]) {
      try { setRows((await api.get(`/clients/${activeClient.id}/${tab}`)).data); }
      catch { setRows([]); }
    }
  };

  useEffect(() => { load(); /* eslint-disable-next-line */ }, [activeClient?.id, tab]);

  if (!activeClient) return <div className="empty">Select a client to view statutory registers.</div>;

  const spec = SPECS[tab];
  const stats = registers.find((r) => r.key === tab);

  const add = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/clients/${activeClient.id}/${tab}`, form);
      onToast(`Added to ${spec.label}`);
      setForm({});
      load();
    } catch (err) {
      onToast(err.response?.data?.detail || "Could not save");
    }
  };

  const remove = async (id) => {
    await api.delete(`/clients/${activeClient.id}/${tab}/${id}`);
    onToast("Removed");
    load();
  };

  const download = (key) => {
    const url = `${API}/clients/${activeClient.id}/registers/${key}.csv`;
    window.open(url, "_blank");
  };

  return (
    <div data-testid="registers-panel">
      <div className="registers-summary" data-testid="registers-summary">
        {registers.map((r) => (
          <div className="register-tile" key={r.key} data-testid={`register-tile-${r.key}`}>
            <div>
              <FileText size={17} />
              <strong>{r.title}</strong>
              <small>{r.count} rows</small>
            </div>
            <button data-testid={`download-${r.key}`} className="button" onClick={() => download(r.key)}>
              <Download size={13} /> CSV
            </button>
          </div>
        ))}
      </div>

      <div className="master-tabs" style={{ marginTop: 24 }}>
        {Object.entries(SPECS).map(([k, v]) => (
          <button key={k} data-testid={`register-tab-${k}`} className={`master-tab ${tab === k ? "active" : ""}`} onClick={() => { setTab(k); setForm({}); }}>
            {v.label} <b>{registers.find((r) => r.key === k)?.count ?? 0}</b>
          </button>
        ))}
      </div>

      <div className="lower-grid">
        <form className="modal-inline" onSubmit={add} data-testid={`register-form-${tab}`}>
          <div className="eyebrow">ADD ENTRY</div>
          <h3>New {spec.label.toLowerCase().replace(/s$/, "")}</h3>
          {spec.fields.map((f) => (
            <label key={f.key}>
              {f.label}{f.required ? " *" : ""}
              <input data-testid={`register-input-${tab}-${f.key}`} type={f.type || "text"} required={f.required}
                value={form[f.key] ?? ""} onChange={(e) => setForm({ ...form, [f.key]: f.type === "number" ? Number(e.target.value) : e.target.value })} />
            </label>
          ))}
          <button data-testid={`register-save-${tab}`} className="button primary">Save entry</button>
        </form>

        <section className="master-list" data-testid={`register-list-${tab}`}>
          {rows.map((row) => (
            <div className="master-row" key={row.id}>
              <div>
                <strong>{row[spec.fields[0].key] || row.name || "Entry"}</strong>
                <small>{spec.fields.slice(1, 4).map((f) => row[f.key]).filter(Boolean).join(" · ")}</small>
              </div>
              <button data-testid={`register-remove-${row.id}`} className="row-action" onClick={() => remove(row.id)}>
                <Trash2 size={13} /> Remove
              </button>
            </div>
          ))}
          {!rows.length && <div className="empty">No entries yet. Add manually or import a workbook.</div>}
        </section>
      </div>
    </div>
  );
}
