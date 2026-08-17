import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { api } from "@/lib/api";

const TABS = [
  { key: "directors", label: "Directors", fields: [
    { key: "name", label: "Name", required: true },
    { key: "din", label: "DIN" },
    { key: "designation", label: "Designation" },
    { key: "appointment_date", label: "Appointed on", type: "date" },
    { key: "cessation_date", label: "Ceased on", type: "date" },
    { key: "kyc_status", label: "KYC status" },
    { key: "email", label: "Email" },
    { key: "pan", label: "PAN" },
  ]},
  { key: "auditors", label: "Auditors", fields: [
    { key: "firm_name", label: "Firm name", required: true },
    { key: "frn", label: "FRN" },
    { key: "appointment_date", label: "Appointed on", type: "date" },
    { key: "term_end_date", label: "Term ends", type: "date" },
    { key: "email", label: "Email" },
    { key: "pan", label: "PAN" },
  ]},
  { key: "financials", label: "Financials", fields: [
    { key: "fy_end", label: "FY ended", required: true },
    { key: "revenue", label: "Revenue", type: "number" },
    { key: "profit", label: "Profit", type: "number" },
    { key: "net_worth", label: "Net worth", type: "number" },
    { key: "paid_up_capital", label: "Paid-up capital", type: "number" },
    { key: "borrowings", label: "Borrowings", type: "number" },
    { key: "turnover", label: "Turnover", type: "number" },
  ]},
];

export default function MasterData({ activeClient, onToast, refreshToken }) {
  const [tab, setTab] = useState("directors");
  const [rows, setRows] = useState({});
  const [form, setForm] = useState({});

  const load = async () => {
    if (!activeClient) return;
    const out = {};
    for (const t of TABS) {
      try { out[t.key] = (await api.get(`/clients/${activeClient.id}/${t.key}`)).data; }
      catch { out[t.key] = []; }
    }
    setRows(out);
  };

  useEffect(() => { load(); }, [activeClient?.id, refreshToken]);

  const current = TABS.find((t) => t.key === tab);
  const list = rows[tab] || [];

  const add = async (e) => {
    e.preventDefault();
    try {
      await api.post(`/clients/${activeClient.id}/${tab}`, form);
      onToast(`Added to ${current.label}`);
      setForm({});
      load();
    } catch (err) {
      onToast(err.response?.data?.detail || "Could not save entry");
    }
  };

  const remove = async (id) => {
    await api.delete(`/clients/${activeClient.id}/${tab}/${id}`);
    onToast("Removed");
    load();
  };

  if (!activeClient) return <div className="empty">Select a client to view master data.</div>;

  return (
    <div data-testid="master-data-panel">
      <div className="master-tabs">
        {TABS.map((t) => (
          <button key={t.key} data-testid={`master-tab-${t.key}`} className={`master-tab ${tab === t.key ? "active" : ""}`} onClick={() => { setTab(t.key); setForm({}); }}>
            {t.label} <b>{(rows[t.key] || []).length}</b>
          </button>
        ))}
      </div>

      <div className="lower-grid">
        <form className="modal-inline" onSubmit={add} data-testid={`master-form-${tab}`}>
          <div className="eyebrow">ADD ENTRY</div>
          <h3>New {current.label.toLowerCase().replace(/s$/, "")}</h3>
          {current.fields.map((f) => (
            <label key={f.key}>
              {f.label}{f.required ? " *" : ""}
              <input data-testid={`master-input-${tab}-${f.key}`} type={f.type || "text"} required={f.required}
                value={form[f.key] || ""} onChange={(e) => setForm({ ...form, [f.key]: f.type === "number" ? Number(e.target.value) : e.target.value })} />
            </label>
          ))}
          <button data-testid={`master-save-${tab}`} className="button primary">Save entry</button>
        </form>

        <section className="master-list" data-testid={`master-list-${tab}`}>
          {list.map((row) => (
            <div className="master-row" key={row.id}>
              <div>
                <strong>{row[current.fields[0].key] || "Unnamed"}</strong>
                <small>{current.fields.slice(1, 4).map((f) => row[f.key]).filter(Boolean).join(" · ")}</small>
              </div>
              <button data-testid={`master-remove-${row.id}`} className="row-action" onClick={() => remove(row.id)}>
                <Trash2 size={13} /> Remove
              </button>
            </div>
          ))}
          {!list.length && <div className="empty">No {current.label.toLowerCase()} yet. Add manually or import a workbook.</div>}
        </section>
      </div>
    </div>
  );
}
