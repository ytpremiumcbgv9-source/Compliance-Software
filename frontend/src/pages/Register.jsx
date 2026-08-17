import { useEffect, useMemo, useState } from "react";
import { ArrowUpRight, Paperclip, PlayCircle, Search, X } from "lucide-react";
import { api } from "@/lib/api";

const STATUSES = ["On track", "Due soon", "Under review", "Overdue", "Ready for review", "Approved", "Rework", "Completed"];
const STATUS_TONE = {
  "Overdue": "danger", "Rework": "danger",
  "Due soon": "warning", "Ready for review": "warning", "Under review": "warning",
  "On track": "success", "Approved": "success", "Completed": "success",
};

function fyOptions() {
  const now = new Date();
  const year = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  return [-1, 0, 1].map((d) => {
    const s = year + d;
    return `${s}-${String((s + 1) % 100).padStart(2, "0")}`;
  });
}

export default function Register({ activeClient, onToast }) {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const [expanded, setExpanded] = useState(null);
  const [fy, setFy] = useState(fyOptions()[1]);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("all");
  const [evidence, setEvidence] = useState({}); // { obligation_id: [files] }

  const load = () => {
    if (!activeClient) return;
    api.get(`/clients/${activeClient.id}/obligations`).then((r) => setItems(r.data));
  };
  useEffect(() => { load(); setEvidence({}); /* eslint-disable-next-line */ }, [activeClient?.id]);

  const loadEvidence = async (obligationId) => {
    const r = await api.get(`/clients/${activeClient.id}/evidence?obligation_id=${obligationId}`);
    setEvidence((prev) => ({ ...prev, [obligationId]: r.data }));
  };

  const uploadEvidence = async (obligationId, file) => {
    const fd = new FormData();
    fd.append("file", file);
    await api.post(`/clients/${activeClient.id}/evidence?obligation_id=${obligationId}`, fd);
    onToast(`Attached ${file.name}`);
    loadEvidence(obligationId);
  };

  const removeEvidence = async (obligationId, evidenceId) => {
    await api.delete(`/clients/${activeClient.id}/evidence/${evidenceId}`);
    onToast("Evidence removed");
    loadEvidence(obligationId);
  };

  const toggleExpanded = (id) => {
    setExpanded(expanded === id ? null : id);
    if (id && !evidence[id]) loadEvidence(id);
  };

  const generate = async () => {
    setBusy(true);
    try {
      const r = await api.post(`/clients/${activeClient.id}/generate-obligations`, { fy });
      onToast(`Created ${r.data.created} obligations for FY ${fy}${r.data.skipped ? `, ${r.data.skipped} already present` : ""}`);
      load();
    } catch (err) {
      onToast(err.response?.data?.detail || "Could not generate");
    } finally {
      setBusy(false);
    }
  };

  const patch = async (id, changes, path = "") => {
    const url = path ? `/obligations/${id}/${path}` : `/obligations/${id}`;
    const r = await api.patch(url, changes);
    setItems((v) => v.map((x) => (x.id === id ? r.data : x)));
    onToast(path === "submit" ? "Sent for review" : path === "review" ? (changes.approved ? "Approved" : "Sent for rework") : "Register updated");
  };

  const shown = useMemo(() => {
    return items.filter((x) => {
      if (filter !== "all" && x.status !== filter) return false;
      const q = query.toLowerCase();
      return (x.name + x.form + (x.assignee || "") + (x.fy || "")).toLowerCase().includes(q);
    });
  }, [items, query, filter]);

  const counts = useMemo(() => {
    return items.reduce((acc, x) => { acc[x.status] = (acc[x.status] || 0) + 1; return acc; }, {});
  }, [items]);

  if (!activeClient) return <div className="empty">Select or create a client to open the register.</div>;

  return (
    <>
      <div className="section-row">
        <div className="section-title"><h2>Compliance register</h2><span className="count">{items.length} tracked</span></div>
        <div className="filters">
          <select data-testid="register-fy-select" className="fy-select" value={fy} onChange={(e) => setFy(e.target.value)}>
            {fyOptions().map((f) => <option key={f} value={f}>FY {f}</option>)}
          </select>
          <button data-testid="generate-fy-button" className="button primary" onClick={generate} disabled={busy}>
            <PlayCircle size={15} /> {busy ? "Generating…" : `Generate FY ${fy}`}
          </button>
          <div className="search"><Search size={15} /><input data-testid="obligation-search-input" placeholder="Search obligations" onChange={(e) => setQuery(e.target.value)} /></div>
        </div>
      </div>

      <div className="chip-row" data-testid="status-chips">
        <button className={`chip ${filter === "all" ? "active" : ""}`} data-testid="chip-all" onClick={() => setFilter("all")}>All <b>{items.length}</b></button>
        {["Overdue", "Ready for review", "Due soon", "On track", "Approved", "Completed"].map((s) => (
          <button key={s} data-testid={`chip-${s.replace(/\s/g, "-").toLowerCase()}`} className={`chip ${filter === s ? "active" : ""} ${STATUS_TONE[s]}`} onClick={() => setFilter(filter === s ? "all" : s)}>
            {s} <b>{counts[s] || 0}</b>
          </button>
        ))}
      </div>

      <section className="register" data-testid="obligation-table">
        <div className="table-head">
          <span>OBLIGATION</span><span>ASSIGNEE</span><span>DUE / FY</span><span>STATUS</span><span>ACTION</span>
        </div>
        {shown.map((x) => (
          <div className="table-row-wrap" key={x.id}>
            <div className="table-row">
              <div className="obligation">
                <span className={`risk-bar ${STATUS_TONE[x.status] || "success"}`} />
                <div><strong data-testid={`obligation-${x.id}-name`}>{x.name}</strong><small>{x.form} · Section {x.section} · {x.category}</small></div>
              </div>
              <span className="owner">
                <input data-testid={`obligation-${x.id}-assignee`} defaultValue={x.assignee || ""} placeholder="Assignee"
                  onBlur={(e) => e.target.value !== (x.assignee || "") && patch(x.id, { assignee: e.target.value })} />
              </span>
              <span className="due"><b>{x.due || "—"}</b><small>{x.fy ? `FY ${x.fy}` : x.recurrence || ""}</small></span>
              <span>
                <select data-testid={`obligation-${x.id}-status`} className={`status-select ${STATUS_TONE[x.status] || "success"}`}
                  value={x.status} onChange={(e) => patch(x.id, { status: e.target.value })}>
                  {STATUSES.map((s) => <option key={s}>{s}</option>)}
                </select>
              </span>
              <button data-testid={`obligation-${x.id}-expand`} className="row-action" onClick={() => toggleExpanded(x.id)}>
                {expanded === x.id ? "Close" : "Open"} <ArrowUpRight size={14} />
              </button>
            </div>
            {expanded === x.id && (
              <div className="obligation-detail" data-testid={`obligation-${x.id}-detail`}>
                <div>
                  <label>Filed date<input data-testid={`obligation-${x.id}-filed`} type="date" defaultValue={x.filed_date || ""} onBlur={(e) => patch(x.id, { filed_date: e.target.value })} /></label>
                  <label>SRN / Ack no.<input data-testid={`obligation-${x.id}-srn`} defaultValue={x.srn || ""} onBlur={(e) => e.target.value !== (x.srn || "") && patch(x.id, { srn: e.target.value })} /></label>
                </div>
                <label>Working remarks<textarea data-testid={`obligation-${x.id}-remarks`} rows="2" defaultValue={x.remarks || ""} onBlur={(e) => e.target.value !== (x.remarks || "") && patch(x.id, { remarks: e.target.value })} /></label>
                <p className="obligation-description">{x.description}</p>
                <div className="evidence-block" data-testid={`evidence-block-${x.id}`}>
                  {(evidence[x.id] || []).map((ev) => (
                    <span key={ev.id} className="evidence-chip" data-testid={`evidence-${ev.id}`}>
                      <Paperclip size={12} /> {ev.filename}
                      <button className="row-action muted" data-testid={`evidence-${ev.id}-remove`} onClick={() => removeEvidence(x.id, ev.id)}><X size={11} /></button>
                    </span>
                  ))}
                  <label className="evidence-upload" data-testid={`evidence-upload-${x.id}`}>
                    <Paperclip size={13} /> Attach evidence
                    <input type="file" hidden data-testid={`evidence-input-${x.id}`} onChange={(e) => e.target.files[0] && uploadEvidence(x.id, e.target.files[0])} />
                  </label>
                </div>
                <div className="maker-checker">
                  {x.status !== "Ready for review" && x.status !== "Approved" && (
                    <button data-testid={`submit-${x.id}`} className="button" onClick={() => patch(x.id, { remarks: x.remarks || "" }, "submit")}>Submit for review</button>
                  )}
                  {x.status === "Ready for review" && (
                    <>
                      <button data-testid={`approve-${x.id}`} className="button primary" onClick={() => patch(x.id, { approved: true }, "review")}>Approve</button>
                      <button data-testid={`rework-${x.id}`} className="button" onClick={() => patch(x.id, { approved: false }, "review")}>Send back</button>
                    </>
                  )}
                  {(x.submitted_by || x.reviewed_by) && (
                    <div className="maker-info">
                      {x.submitted_by && <small>Submitted by <b>{x.submitted_by}</b></small>}
                      {x.reviewed_by && <small>Reviewed by <b>{x.reviewed_by}</b></small>}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        ))}
        {!shown.length && (
          <div className="empty">
            {items.length === 0
              ? <>No obligations yet for this client. Pick a financial year above and click <b>Generate FY</b> to load the statutory calendar (15 filings) in one shot.</>
              : "No obligations match your filter."}
          </div>
        )}
      </section>
    </>
  );
}
