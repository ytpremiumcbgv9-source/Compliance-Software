import { useState } from "react";
import { ArrowUpRight, FileSpreadsheet, FileUp } from "lucide-react";
import { api } from "@/lib/api";

const TARGET_LABEL = {
  directors: "Directors register",
  auditors: "Auditors register",
  financials: "Financial inputs",
};

export default function ImportWizard({ activeClient, onToast, refreshMasterCounts }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sheetState, setSheetState] = useState({}); // sheetName -> {target, mapping, applied?}

  const scan = async () => {
    if (!file) return;
    setBusy(true);
    try {
      const f = new FormData();
      f.append("file", file);
      const r = await api.post("/imports/preview", f);
      setPreview(r.data);
      const initial = {};
      for (const s of r.data.sheets) {
        initial[s.name] = { target: s.suggested_target, mapping: { ...s.suggested_mapping } };
      }
      setSheetState(initial);
      onToast(`Scanned ${r.data.sheets.length} sheet(s) from ${r.data.filename}`);
    } catch (err) {
      onToast(err.response?.data?.detail || "Could not scan workbook");
    } finally {
      setBusy(false);
    }
  };

  const changeTarget = (sheet, target) => {
    const s = preview.sheets.find((x) => x.name === sheet);
    const suggested = { directors: {}, auditors: {}, financials: {} };
    setSheetState((prev) => ({ ...prev, [sheet]: { target, mapping: {}, applied: false } }));
    // Fresh auto-suggest by asking backend? Keep simple: clear and let user pick.
  };

  const changeMapping = (sheet, field, column) => {
    setSheetState((prev) => ({
      ...prev,
      [sheet]: { ...prev[sheet], mapping: { ...prev[sheet].mapping, [field]: column } },
    }));
  };

  const apply = async (sheet) => {
    if (!activeClient) { onToast("Select a client workspace first"); return; }
    const state = sheetState[sheet];
    const sheetData = preview.sheets.find((s) => s.name === sheet);
    const rows = sheetData.rows.map((row) => {
      const out = {};
      for (const [field, col] of Object.entries(state.mapping)) {
        if (col && col in row) out[field] = row[col];
      }
      return out;
    });
    const r = await api.post("/imports/apply", {
      client_id: activeClient.id,
      target: state.target,
      rows,
    });
    setSheetState((prev) => ({ ...prev, [sheet]: { ...prev[sheet], applied: true, result: r.data } }));
    onToast(r.data.message);
    refreshMasterCounts?.();
  };

  return (
    <div className="import-layout" data-testid="import-panel">
      <div className="import-hero">
        <FileSpreadsheet size={24} />
        <div>
          <h2>Bring your source data, not your workbook</h2>
          <p>Upload financials, ROC master data, director lists, or other Excel files. ComplyEase reads every tab, suggests where each column belongs, and writes real records into your client workspace.</p>
        </div>
      </div>

      <label data-testid="source-workbook-dropzone" className="upload-zone">
        <FileUp size={21} />
        <div>
          <strong>{file ? file.name : "Choose a source Excel file"}</strong>
          <small>Directors · Auditors · Financial figures · ROC master data</small>
        </div>
        <span className="button secondary">
          Browse
          <input data-testid="source-workbook-input" type="file" accept=".xlsx,.xls" hidden onChange={(e) => setFile(e.target.files[0])} />
        </span>
      </label>

      <button data-testid="scan-workbook-button" className="button primary" disabled={!file || busy} onClick={scan}>
        {busy ? "Scanning…" : "Scan workbook"} <ArrowUpRight size={16} />
      </button>

      {preview && preview.sheets.map((s) => {
        const state = sheetState[s.name] || {};
        const targetFields = preview.targets[state.target] || [];
        return (
          <div key={s.name} className="import-sheet" data-testid={`import-sheet-${s.name}`}>
            <div className="import-sheet-head">
              <div>
                <strong>{s.name}</strong>
                <small>{s.rows_count} rows · {s.columns.length} columns</small>
              </div>
              <label className="import-target">
                Import as
                <select data-testid={`import-target-${s.name}`} value={state.target || ""} onChange={(e) => changeTarget(s.name, e.target.value)}>
                  {Object.keys(preview.targets).map((t) => <option key={t} value={t}>{TARGET_LABEL[t]}</option>)}
                </select>
              </label>
              <button data-testid={`import-apply-${s.name}`} className="button primary" onClick={() => apply(s.name)} disabled={state.applied}>
                {state.applied ? `Imported (${state.result?.inserted || 0})` : "Apply mapping"}
              </button>
            </div>
            <div className="import-map">
              {targetFields.map((field) => (
                <label key={field}>
                  {field.replace(/_/g, " ")}
                  <select data-testid={`import-map-${s.name}-${field}`} value={state.mapping?.[field] || ""} onChange={(e) => changeMapping(s.name, field, e.target.value)}>
                    <option value="">— skip —</option>
                    {s.columns.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </label>
              ))}
            </div>
            <details>
              <summary>Preview first rows</summary>
              <table className="preview-table">
                <thead><tr>{s.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
                <tbody>
                  {s.sample.map((row, i) => (
                    <tr key={i}>{s.columns.map((c) => <td key={c}>{String(row[c] ?? "")}</td>)}</tr>
                  ))}
                </tbody>
              </table>
            </details>
          </div>
        );
      })}
    </div>
  );
}
