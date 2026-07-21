import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppShell from "@/components/AppShell";
import { inr, STATUS_LABELS } from "@/lib/format";
import { RegimeCompareChart } from "@/components/charts/Charts";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";
import {
  ArrowLeft, FileText, Download, Pencil, Lock, AlertTriangle, ShieldCheck,
  CheckCircle2, Loader2, ScanLine, FileJson, FileDown, Crosshair,
  ChevronLeft, ChevronRight,
} from "lucide-react";

const links = [{ to: "/ca", label: "Dashboard" }, { to: "/ca/audit", label: "Audit Trails" }];

const FIELD_LABELS = {
  gross_salary: "Gross Salary (u/s 17(1))",
  section_10_exemptions: "Section 10 Exemptions",
  deductions_80c: "Deductions u/s 80C",
  deductions_80d: "Deductions u/s 80D",
  other_income: "Other Income",
  tds_deducted: "TDS Deducted",
  stcg_equity: "STCG Equity",
  ltcg_equity: "LTCG Equity",
};

export default function ClientDesk() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [filing, setFiling] = useState(null);
  const [docs, setDocs] = useState([]);
  const [logs, setLogs] = useState([]);
  const [candidates, setCandidates] = useState([]);
  const [workflowBusy, setWorkflowBusy] = useState(false);
  const [activeDoc, setActiveDoc] = useState(null);
  const [meta, setMeta] = useState(null);          // {is_pdf, page_count, pages}
  const [page, setPage] = useState(0);
  const [pageImg, setPageImg] = useState(null);
  const [highlights, setHighlights] = useState([]);
  const [override, setOverride] = useState(null);
  const [justification, setJustification] = useState("");
  const [saving, setSaving] = useState(false);
  const [locking, setLocking] = useState(false);
  const [parsingId, setParsingId] = useState(null);
  const [aisOpen, setAisOpen] = useState(false);
  const [aisFile, setAisFile] = useState(null);
  const [pan, setPan] = useState("");
  const [dob, setDob] = useState("");
  const [aisBusy, setAisBusy] = useState(false);

  const load = useCallback(async () => {
    const f = await api.get(`/filings/${id}`);
    setFiling(f.data);
    const [d, l, candidateResponse] = await Promise.all([
      api.get(`/documents?user_id=${f.data.user_id}`),
      api.get(`/filings/${id}/audit-logs`),
      api.get(`/filings/${id}/facts/candidates`),
    ]);
    setDocs(d.data);
    setLogs([...(l.data.events || []), ...(l.data.legacy_events || [])]);
    setCandidates(candidateResponse.data || []);
    if (d.data[0]) selectDoc(d.data[0]);
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const selectDoc = async (doc) => {
    setActiveDoc(doc); setHighlights([]); setPage(0);
    try {
      const info = await api.get(`/documents/${doc.id}/info`);
      setMeta(info.data);
      if (info.data.is_pdf) await loadPage(doc.id, 0);
      else {
        const r = await api.get(`/documents/${doc.id}/download`, { responseType: "blob" });
        setPageImg(URL.createObjectURL(r.data));
      }
    } catch { toast.error("Cannot load document"); }
  };

  const loadPage = async (docId, n) => {
    const r = await api.get(`/documents/${docId}/page/${n}`, { responseType: "blob" });
    setPageImg(URL.createObjectURL(r.data));
    setPage(n);
  };

  const locate = async (field) => {
    if (!activeDoc || !meta?.is_pdf) { toast.message("Highlighting works on PDF documents"); return; }
    const term = String(filing.parsed_payload?.[field] ?? "");
    if (!term || term === "0") { toast.message("No value to locate"); return; }
    try {
      const r = await api.post(`/documents/${activeDoc.id}/locate`, { term });
      if (!r.data.rects.length) { toast.message("Value not found in document text"); setHighlights([]); return; }
      if (r.data.page !== page) await loadPage(activeDoc.id, r.data.page);
      setHighlights(r.data.rects);
    } catch { toast.error("Locate failed"); }
  };

  const parse = async (docId) => {
    setParsingId(docId);
    try { await api.post(`/documents/${docId}/parse`); toast.success("Extraction complete"); await load(); }
    catch { toast.error("Parse failed"); }
    finally { setParsingId(null); }
  };

  const submitOverride = async () => {
    if (!justification.trim()) { toast.error("Justification is mandatory for the audit log"); return; }
    setSaving(true);
    try {
      await api.post("/validation/override-field", {
        state_id: id, target_field: override.field, new_value: Number(override.value) || 0, justification,
      });
      toast.success("Override candidate created for reviewer approval");
      setOverride(null); setJustification(""); await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Override failed"); }
    finally { setSaving(false); }
  };


  const reviewCandidate = async (candidateId, decision) => {
    const justification = window.prompt(`Reason for ${decision.toLowerCase()}ing this candidate:`);
    if (!justification || justification.trim().length < 8) { toast.error("A meaningful review reason is required"); return; }
    setWorkflowBusy(true);
    try {
      await api.post(`/filings/${id}/facts/candidates/${candidateId}/review`, { decision, justification });
      toast.success(`Candidate ${decision === "ACCEPT" ? "accepted" : "rejected"}`);
      await load();
    } catch (e) { toast.error(e.response?.data?.detail || "Candidate review failed"); }
    finally { setWorkflowBusy(false); }
  };

  const computeApproved = async () => {
    setWorkflowBusy(true);
    try { await api.post(`/filings/${id}/compute-approved`); toast.success("Computed from approved facts"); await load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Approved-fact computation failed"); }
    finally { setWorkflowBusy(false); }
  };

  const approveForm = async () => {
    setWorkflowBusy(true);
    try { await api.post(`/filings/${id}/form-eligibility/review`); toast.success("Return-form eligibility approved"); await load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Form review failed"); }
    finally { setWorkflowBusy(false); }
  };

  const approveFinalReview = async () => {
    setWorkflowBusy(true);
    try { await api.post(`/filings/${id}/final-review`); toast.success("Final computation review approved"); await load(); }
    catch (e) { toast.error(e.response?.data?.detail || "Final review failed"); }
    finally { setWorkflowBusy(false); }
  };

  const uploadAis = async () => {
    if (!aisFile) { toast.error("Choose the AIS JSON file"); return; }
    setAisBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", aisFile); fd.append("pan", pan); fd.append("dob", dob);
      const r = await api.post(`/filings/${id}/upload-ais`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setFiling((f) => ({ ...f, reconciliation_discrepancies: r.data.discrepancies, status: r.data.status }));
      toast.success(r.data.discrepancies.length ? `${r.data.discrepancies.length} mismatches flagged` : "AIS reconciled — clean");
      setAisOpen(false);
    } catch (e) { toast.error(e.response?.data?.detail || "AIS decryption failed"); }
    finally { setAisBusy(false); }
  };

  const lock = async () => {
    setLocking(true);
    try { const r = await api.post(`/filings/${id}/lock`); setFiling(r.data); toast.success("Approved computation snapshot locked"); }
    catch (e) { toast.error(e.response?.data?.detail || "Lock failed"); }
    finally { setLocking(false); }
  };

  const blobDownload = async (path, filename, type) => {
    const r = await api.get(path, { responseType: "blob" });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a"); a.href = url; a.download = filename; a.click();
    URL.revokeObjectURL(url);
  };

  const exportJson = async () => {
    try {
      const r = await api.get(`/filings/${id}/internal-audit-export`);
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `Audit_${id.slice(0, 6)}.json`; a.click();
      URL.revokeObjectURL(url);
    } catch (e) { toast.error(e.response?.data?.detail || "Audit export unavailable"); }
  };

  if (!filing) return <AppShell links={links}><div className="text-slate-ink">Loading desk…</div></AppShell>;
  const p = filing.parsed_payload || {};
  const c = filing.tax_computation_summary;
  const flags = filing.reconciliation_discrepancies || [];
  const dims = meta?.pages?.[page];

  return (
    <AppShell links={links}>
      <button onClick={() => navigate("/ca")} className="flex items-center gap-2 text-slate-ink hover:text-graphite text-sm mb-5" data-testid="back-to-hub">
        <ArrowLeft className="h-4 w-4" /> Back to hub
      </button>

      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <p className="text-brass font-display text-sm">Client desk · {filing.selected_itr_form}</p>
          <h1 className="heading-lg text-graphite mt-1">{filing.user_name}</h1>
          <p className="text-slate-ink text-sm">{filing.user_email}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs px-3 py-1.5 rounded-full bg-ash font-display text-graphite">{STATUS_LABELS[filing.status]}</span>
          <button onClick={() => setAisOpen(true)} data-testid="desk-ais-btn" className="font-display text-sm border border-graphite text-graphite px-4 py-2.5 rounded-none hover:bg-graphite hover:text-white transition-colors">Validate with AIS</button>
          <button onClick={() => blobDownload(`/filings/${id}/computation-pdf`, `Computation_${id.slice(0,6)}.pdf`)} data-testid="desk-pdf-btn" className="font-display text-sm border border-graphite text-graphite px-4 py-2.5 rounded-none hover:bg-graphite hover:text-white transition-colors flex items-center gap-2"><FileDown className="h-4 w-4" /> PDF</button>
          {filing.locked ? (
            <button onClick={exportJson} data-testid="desk-export-btn" className="font-display text-sm bg-graphite text-white px-4 py-2.5 rounded-none hover:bg-ember transition-colors flex items-center gap-2"><FileJson className="h-4 w-4" /> Audit package</button>
          ) : (
            <button onClick={lock} disabled={locking} data-testid="lock-compile-btn" className="font-display text-sm bg-graphite text-white px-4 py-2.5 rounded-none hover:bg-ember transition-colors flex items-center gap-2 disabled:opacity-60">
              {locking ? <Loader2 className="h-4 w-4 animate-spin" /> : <Lock className="h-4 w-4" />} Lock approved snapshot
            </button>
          )}
        </div>
      </div>

      {!filing.locked && (
        <div className="mb-6 bg-ash card-asym p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-display text-lg text-graphite">Controlled review workflow</h3>
              <p className="text-steel text-sm mt-1">Accept evidence candidates, compute approved facts, approve the form, complete final review, then lock.</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button disabled={workflowBusy} onClick={computeApproved} className="font-display text-sm border border-graphite px-3 py-2 hover:bg-graphite hover:text-white disabled:opacity-50">Compute approved facts</button>
              <button disabled={workflowBusy} onClick={approveForm} className="font-display text-sm border border-graphite px-3 py-2 hover:bg-graphite hover:text-white disabled:opacity-50">Approve form</button>
              <button disabled={workflowBusy} onClick={approveFinalReview} className="font-display text-sm border border-graphite px-3 py-2 hover:bg-graphite hover:text-white disabled:opacity-50">Final review</button>
            </div>
          </div>
        </div>
      )}

      {candidates.filter((item) => ["PENDING_REVIEW", "CONFLICTING", "VALIDATED"].includes(item.status)).length > 0 && (
        <div className="mb-6 bg-white border border-mist rounded-lg p-5">
          <h3 className="font-display text-lg text-graphite">Candidate facts awaiting review</h3>
          <p className="text-steel text-sm mt-1 mb-4">Extraction and manual overrides cannot affect tax until an authorised reviewer accepts them.</p>
          <div className="space-y-2">
            {candidates.filter((item) => ["PENDING_REVIEW", "CONFLICTING", "VALIDATED"].includes(item.status)).map((item) => (
              <div key={item.candidate_fact_id} className="flex flex-wrap items-center justify-between gap-3 border border-mist p-3">
                <div>
                  <div className="font-display text-graphite text-sm">{item.field_code}</div>
                  <div className="text-steel text-sm">{item.value_type === "money" ? inr(Number(item.value?.amount || 0)) : String(item.value)}</div>
                </div>
                <div className="flex gap-2">
                  <button disabled={workflowBusy} onClick={() => reviewCandidate(item.candidate_fact_id, "ACCEPT")} className="text-sm font-display bg-graphite text-white px-3 py-1.5 disabled:opacity-50">Accept</button>
                  <button disabled={workflowBusy} onClick={() => reviewCandidate(item.candidate_fact_id, "REJECT")} className="text-sm font-display border border-graphite px-3 py-1.5 disabled:opacity-50">Reject</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {flags.length > 0 && (
        <div className="mb-6 space-y-2" data-testid="desk-alerts">
          {flags.map((f, i) => (
            <div key={i} className={`flex items-start gap-3 rounded-lg p-4 bg-white border ${f.severity === "HIGH" ? "border-ember" : "border-mist"}`}>
              <AlertTriangle className={`h-4 w-4 mt-0.5 ${f.severity === "HIGH" ? "text-ember" : "text-brass"}`} />
              <div><span className="font-display text-graphite text-sm">{f.field} · {f.severity}</span><p className="text-steel text-sm">{f.message}</p></div>
            </div>
          ))}
        </div>
      )}

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Left: document vault with highlight overlay */}
        <div className="bg-white border border-mist rounded-lg p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-display text-lg text-graphite">Secure document vault</h3>
            {activeDoc && <button onClick={() => window.open(pageImg, "_blank")} data-testid="download-doc-btn" className="text-sm text-graphite flex items-center gap-1.5 hover:text-ember"><Download className="h-4 w-4" /> Open</button>}
          </div>
          <div className="flex flex-wrap gap-2 mb-4">
            {docs.map((d) => (
              <div key={d.id} className={`flex items-center gap-2 px-3 py-1.5 text-xs font-display ${activeDoc?.id === d.id ? "bg-graphite text-white" : "bg-ash text-graphite"}`}>
                <button onClick={() => selectDoc(d)} className="flex items-center gap-1.5"><FileText className="h-3.5 w-3.5" /> {d.file_name.slice(0, 16)}</button>
                <button onClick={() => parse(d.id)} disabled={parsingId === d.id} title="Parse" className={activeDoc?.id === d.id ? "text-white hover:text-ember" : "text-brass hover:text-ember"}>
                  {parsingId === d.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ScanLine className="h-3.5 w-3.5" />}
                </button>
              </div>
            ))}
          </div>

          {meta?.is_pdf && meta.page_count > 1 && (
            <div className="flex items-center justify-center gap-3 mb-3 text-sm">
              <button onClick={() => loadPage(activeDoc.id, Math.max(0, page - 1))} disabled={page === 0} className="text-graphite disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
              <span className="font-display text-slate-ink">Page {page + 1} / {meta.page_count}</span>
              <button onClick={() => loadPage(activeDoc.id, Math.min(meta.page_count - 1, page + 1))} disabled={page >= meta.page_count - 1} className="text-graphite disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
            </div>
          )}

          <div className="bg-fog rounded-md h-[560px] overflow-auto border border-mist" data-testid="doc-preview">
            {!pageImg ? (
              <div className="h-full flex items-center justify-center text-slate-ink text-sm">No document to preview</div>
            ) : (
              <div className="relative" style={{ width: "100%" }}>
                <img src={pageImg} alt="document" className="w-full block" data-testid="doc-page-image" />
                {dims && highlights.map((r, i) => (
                  <div key={i} className="absolute border-2 border-ember bg-ember/20 pointer-events-none" data-testid="highlight-box"
                    style={{
                      left: `${(r[0] / dims.width) * 100}%`, top: `${(r[1] / dims.height) * 100}%`,
                      width: `${((r[2] - r[0]) / dims.width) * 100}%`, height: `${((r[3] - r[1]) / dims.height) * 100}%`,
                    }} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: extractions */}
        <div className="space-y-6">
          <div className="bg-white border border-mist rounded-lg p-5">
            <h3 className="font-display text-lg text-graphite mb-4">AI extractions {filing.locked && <span className="text-xs text-brass">· locked</span>}</h3>
            <div className="space-y-2.5" data-testid="extraction-fields">
              {Object.keys(FIELD_LABELS).map((k) => (
                <div key={k} className="flex items-center justify-between border border-mist rounded-md px-4 py-2.5">
                  <span className="text-sm text-steel">{FIELD_LABELS[k]}</span>
                  <div className="flex items-center gap-3">
                    <span className="font-display text-graphite">{inr(p[k] || 0)}</span>
                    <button onClick={() => locate(k)} data-testid={`locate-${k}`} title="Highlight in document" className="text-slate-ink hover:text-ember"><Crosshair className="h-3.5 w-3.5" /></button>
                    {!filing.locked && (
                      <button onClick={() => { setOverride({ field: k, value: p[k] || 0 }); setJustification(""); }}
                        data-testid={`edit-${k}`} className="text-slate-ink hover:text-ember"><Pencil className="h-3.5 w-3.5" /></button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {c && (
            <div className="bg-white border border-mist rounded-lg p-5">
              <div className="flex items-center justify-between mb-2">
                <h3 className="font-display text-lg text-graphite">Computed liability</h3>
                <span className="text-xs px-2 py-1 bg-ivory text-brass rounded-full font-display">Recommended: {c.recommended_regime}</span>
              </div>
              <RegimeCompareChart oldTax={c.tax_liability_old} newTax={c.tax_liability_new} />
            </div>
          )}
        </div>
      </div>

      <div className="mt-8 bg-ash card-asym p-6">
        <div className="flex items-center gap-2 mb-4"><ShieldCheck className="h-5 w-5 text-graphite" /><h3 className="font-display text-lg text-graphite">Audit trail (this filing)</h3></div>
        {logs.length === 0 ? <p className="text-steel text-sm">No modifications logged yet.</p> : (
          <div className="space-y-2" data-testid="desk-audit-logs">
            {logs.slice(0, 8).map((l, index) => (
              <div key={l.event_id || l.id || index} className="bg-white rounded-md px-4 py-3 text-sm">
                <div className="flex items-center gap-2"><CheckCircle2 className="h-3.5 w-3.5 text-brass" /><span className="font-display text-graphite">{l.action || l.modified_field || "Case event"}</span></div>
                <p className="text-steel text-xs mt-1 pl-5">{l.metadata?.justification || l.justification || `${l.entity_type || "record"} ${l.entity_id || ""}`}</p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Override dialog */}
      <Dialog open={!!override} onOpenChange={(o) => !o && setOverride(null)}>
        <DialogContent data-testid="override-dialog">
          <DialogHeader><DialogTitle className="font-display">Override {override && FIELD_LABELS[override.field]}</DialogTitle>
          <DialogDescription>Enter the corrected value and a mandatory justification recorded to the immutable audit log.</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <label className="block">
              <span className="text-xs text-steel font-display">New value</span>
              <input type="number" value={override?.value ?? ""} onChange={(e) => setOverride({ ...override, value: e.target.value })}
                data-testid="override-value" className="w-full mt-1 border border-mist rounded-md px-3 py-2 text-sm focus:border-graphite focus:outline-none" />
            </label>
            <label className="block">
              <span className="text-xs text-steel font-display">Justification (mandatory for ICAI audit log)</span>
              <textarea value={justification} onChange={(e) => setJustification(e.target.value)} rows={3}
                data-testid="override-justification" placeholder="e.g. Included under 80C based on manual investment proof reviewed."
                className="w-full mt-1 border border-mist rounded-md px-3 py-2 text-sm focus:border-graphite focus:outline-none" />
            </label>
          </div>
          <DialogFooter>
            <button onClick={submitOverride} disabled={saving} data-testid="override-submit"
              className="font-display bg-graphite text-white px-5 py-2.5 rounded-none hover:bg-ember transition-colors flex items-center gap-2 disabled:opacity-60">
              {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null} Create review candidate
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* AIS dialog */}
      <Dialog open={aisOpen} onOpenChange={setAisOpen}>
        <DialogContent data-testid="ais-dialog">
          <DialogHeader><DialogTitle className="font-display">Validate with AIS</DialogTitle>
          <DialogDescription>Upload the client's AIS JSON from the ITD portal (encrypted utility file or decrypted JSON). Decryption runs server-side.</DialogDescription></DialogHeader>
          <div className="space-y-3">
            <input type="file" accept=".json,.txt" onChange={(e) => setAisFile(e.target.files[0])} data-testid="ais-file-input"
              className="w-full text-sm file:mr-3 file:border-0 file:bg-graphite file:text-white file:px-3 file:py-2 file:font-display border border-mist bg-white" />
            <div className="grid grid-cols-2 gap-3">
              <input value={pan} onChange={(e) => setPan(e.target.value.toUpperCase())} placeholder="PAN (ABCDE1234F)" data-testid="ais-pan"
                className="border border-mist rounded-md px-3 py-2 text-sm focus:border-graphite focus:outline-none" />
              <input value={dob} onChange={(e) => setDob(e.target.value)} placeholder="DOB ddmmyyyy" data-testid="ais-dob"
                className="border border-mist rounded-md px-3 py-2 text-sm focus:border-graphite focus:outline-none" />
            </div>
          </div>
          <DialogFooter>
            <button onClick={uploadAis} disabled={aisBusy} data-testid="upload-ais-btn"
              className="font-display bg-graphite text-white px-5 py-2.5 rounded-none hover:bg-ember transition-colors flex items-center gap-2 disabled:opacity-60">
              {aisBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Decrypt & reconcile
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AppShell>
  );
}
