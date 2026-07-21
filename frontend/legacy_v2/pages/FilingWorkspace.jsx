import { useEffect, useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppShell from "@/components/AppShell";
import { inr, STATUS_LABELS } from "@/lib/format";
import { RegimeCompareChart, SlabUtilChart, DeductionDonut } from "@/components/charts/Charts";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";
import {
  ArrowLeft, UploadCloud, FileText, Sparkles, Loader2, CheckCircle2,
  AlertTriangle, Send, Download, ScanLine, TrendingDown, Layers, ShieldCheck, FileDown,
} from "lucide-react";

const links = [{ to: "/dashboard", label: "My Filings" }];

const FIELDS = [
  ["gross_salary", "Gross salary (u/s 17(1))"],
  ["section_10_exemptions", "Section 10 exemptions (HRA/LTA)"],
  ["deductions_80c", "Deductions u/s 80C"],
  ["deductions_80d", "Deductions u/s 80D"],
  ["other_income", "Other income (interest/dividend)"],
  ["house_property_income", "House property income"],
  ["stcg_equity", "STCG equity"],
  ["ltcg_equity", "LTCG equity"],
  ["tds_deducted", "TDS deducted"],
];

export default function FilingWorkspace() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [filing, setFiling] = useState(null);
  const [docs, setDocs] = useState([]);
  const [form, setForm] = useState({});
  const [uploading, setUploading] = useState(false);
  const [parsingId, setParsingId] = useState(null);
  const [parsingAll, setParsingAll] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tab, setTab] = useState("documents");
  const [aisFile, setAisFile] = useState(null);
  const [pan, setPan] = useState("");
  const [dob, setDob] = useState("");
  const [aisBusy, setAisBusy] = useState(false);

  const load = useCallback(async () => {
    const [f, d] = await Promise.all([api.get(`/filings/${id}`), api.get("/documents")]);
    setFiling(f.data);
    setForm(f.data.parsed_payload || {});
    setDocs(d.data.filter((x) => x.filing_id === id));
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const upload = async (fileList) => {
    const files = Array.from(fileList || []);
    if (!files.length) return;
    setUploading(true);
    try {
      for (const file of files) {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("document_type", "form_16");
        fd.append("filing_id", id);
        const r = await api.post("/documents/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
        setDocs((p) => [r.data, ...p]);
      }
      toast.success(`${files.length} document(s) uploaded to secure vault`);
    } catch { toast.error("Upload failed"); }
    finally { setUploading(false); }
  };

  const parseAll = async () => {
    setParsingAll(true);
    try {
      const r = await api.post(`/filings/${id}/parse-documents`);
      const candidates = (r.data.outcomes || []).reduce((sum, item) => sum + (item.candidate_fact_count || 0), 0);
      toast.success(`${r.data.documents_analyzed} document(s) parsed · ${candidates} candidate facts created for review`);
      await load();
      setTab("documents");
    } catch (e) { toast.error(e.response?.data?.detail || "Consolidated parse failed"); }
    finally { setParsingAll(false); }
  };

  const uploadAis = async () => {
    if (!aisFile) { toast.error("Choose your AIS JSON file"); return; }
    setAisBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", aisFile);
      fd.append("pan", pan);
      fd.append("dob", dob);
      const r = await api.post(`/filings/${id}/upload-ais`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setFiling((f) => ({ ...f, reconciliation_discrepancies: r.data.discrepancies, ais_prefill: r.data.ais_prefill, status: r.data.status }));
      toast.success(r.data.discrepancies.length ? `${r.data.discrepancies.length} discrepancies flagged` : "AIS reconciled — no mismatches");
    } catch (e) { toast.error(e.response?.data?.detail || "AIS upload/decryption failed"); }
    finally { setAisBusy(false); }
  };

  const downloadPdf = async () => {
    const r = await api.get(`/filings/${id}/computation-pdf`, { responseType: "blob" });
    const url = URL.createObjectURL(r.data);
    const a = document.createElement("a");
    a.href = url; a.download = `GreenPapaya_Computation_${id.slice(0, 6)}.pdf`; a.click();
    URL.revokeObjectURL(url);
    toast.success("Computation PDF downloaded");
  };

  const parse = async (docId) => {
    setParsingId(docId);
    try {
      const r = await api.post(`/documents/${docId}/parse`);
      const p = r.data.parsed_json;
      toast.success(`Parsed with ${r.data.confidence_score}% confidence`);
      setDocs((prev) => prev.map((d) => d.id === docId ? { ...d, parsed_json: p, confidence_score: r.data.confidence_score } : d));
      // merge extracted values into form
      setForm((prev) => {
        const next = { ...prev };
        ["gross_salary", "section_10_exemptions", "deductions_80c", "deductions_80d", "tds_deducted", "stcg_equity", "ltcg_equity"].forEach((k) => {
          if (p[k]) next[k] = p[k];
        });
        return next;
      });
      await load();
      setTab("optimize");
    } catch { toast.error("Parsing failed — check the document"); }
    finally { setParsingId(null); }
  };

  const save = async () => {
    setSaving(true);
    try {
      const payload = {};
      Object.entries(form).forEach(([k, v]) => { payload[k] = Number(v) || 0; });
      const r = await api.put(`/filings/${id}`, { parsed_payload: payload });
      setFiling(r.data);
      toast.success("Computation updated");
    } catch { toast.error("Save failed"); }
    finally { setSaving(false); }
  };

  const setRegime = async (regime) => {
    const r = await api.put(`/filings/${id}`, { selected_regime: regime });
    setFiling(r.data);
  };

  const request = async () => {
    try {
      const r = await api.post(`/filings/${id}/request-verification`);
      setFiling(r.data);
      toast.success(r.data.assigned_ca_id ? "Sent to your linked CA for review" : "Marked for review (no CA linked yet)");
    } catch { toast.error("Failed"); }
  };

  const exportJson = async () => {
    try {
      const r = await api.get(`/filings/${id}/internal-audit-export`);
      const blob = new Blob([JSON.stringify(r.data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = `GreenPapaya_Audit_${id.slice(0, 6)}.json`; a.click();
      URL.revokeObjectURL(url);
      toast.success("Internal audit package downloaded");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Approved-fact computation required before export");
    }
  };

  if (!filing) return <AppShell links={links}><div className="text-slate-ink">Loading…</div></AppShell>;

  const c = filing.tax_computation_summary;
  const dedItems = [
    { name: "80C", value: Math.min(Number(form.deductions_80c) || 0, 150000), color: "#202020" },
    { name: "80D", value: Number(form.deductions_80d) || 0, color: "#ff682c" },
    { name: "Sec 10 (HRA/LTA)", value: Number(form.section_10_exemptions) || 0, color: "#816729" },
  ];

  return (
    <AppShell links={links}>
      <button onClick={() => navigate("/dashboard")} className="flex items-center gap-2 text-slate-ink hover:text-graphite text-sm mb-5" data-testid="back-btn">
        <ArrowLeft className="h-4 w-4" /> Back to filings
      </button>

      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <p className="text-brass font-display text-sm">{filing.assessment_year} · {filing.selected_itr_form}</p>
          <h1 className="heading-lg text-graphite mt-1">Filing workspace</h1>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs px-3 py-1.5 rounded-full bg-ash font-display text-graphite">{STATUS_LABELS[filing.status]}</span>
          <button onClick={request} data-testid="request-verification-btn"
            className="font-display text-[15px] bg-graphite text-white px-5 py-2.5 rounded-none hover:bg-ember transition-colors flex items-center gap-2">
            <Send className="h-4 w-4" /> Request CA verification
          </button>
        </div>
      </div>

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList className="bg-ash rounded-none p-1 mb-6">
          <TabsTrigger value="documents" data-testid="tab-documents" className="rounded-none font-display data-[state=active]:bg-white">Documents</TabsTrigger>
          <TabsTrigger value="optimize" data-testid="tab-optimize" className="rounded-none font-display data-[state=active]:bg-white">Optimize</TabsTrigger>
          <TabsTrigger value="reconcile" data-testid="tab-reconcile" className="rounded-none font-display data-[state=active]:bg-white">Reconcile</TabsTrigger>
          <TabsTrigger value="export" data-testid="tab-export" className="rounded-none font-display data-[state=active]:bg-white">Export</TabsTrigger>
        </TabsList>

        {/* DOCUMENTS */}
        <TabsContent value="documents" className="space-y-6">
          <label className="block bg-ash card-asym p-10 text-center cursor-pointer hover:bg-ivory transition-colors" data-testid="upload-zone">
            <input type="file" accept=".pdf,.png,.jpg,.jpeg" multiple hidden onChange={(e) => upload(e.target.files)} data-testid="file-input" />
            <div className="h-14 w-14 mx-auto bg-white border border-mist flex items-center justify-center">
              {uploading ? <Loader2 className="h-6 w-6 animate-spin text-graphite" /> : <UploadCloud className="h-6 w-6 text-graphite" strokeWidth={1.5} />}
            </div>
            <h3 className="font-display text-xl text-graphite mt-5">Drop your Form 16 or broker statement</h3>
            <p className="text-steel mt-2 text-sm">PDF, PNG or JPG · select multiple pages/photos of the same form · converted into reviewable candidate facts</p>
          </label>

          {docs.length > 1 && (
            <button onClick={parseAll} disabled={parsingAll} data-testid="parse-all-btn"
              className="w-full font-display bg-graphite text-white px-5 py-3 rounded-none hover:bg-ember transition-colors flex items-center justify-center gap-2 disabled:opacity-60">
              {parsingAll ? <><Loader2 className="h-4 w-4 animate-spin" /> Consolidating {docs.length} files…</> : <><Layers className="h-4 w-4" /> Parse all {docs.length} documents into review candidates</>}
            </button>
          )}

          <div className="space-y-3" data-testid="documents-list">
            {docs.length === 0 && <p className="text-slate-ink text-sm">No documents uploaded yet.</p>}
            {docs.map((d) => (
              <div key={d.id} className="bg-white border border-mist rounded-lg p-5 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="h-10 w-10 bg-ash flex items-center justify-center shrink-0"><FileText className="h-5 w-5 text-graphite" /></div>
                  <div className="min-w-0">
                    <div className="font-display text-graphite truncate">{d.file_name}</div>
                    <div className="text-xs text-slate-ink">
                      {d.parsed_json ? <span className="text-brass">Parsed · {d.confidence_score}% confidence</span> : "Not parsed yet"}
                    </div>
                  </div>
                </div>
                <button onClick={() => parse(d.id)} disabled={parsingId === d.id} data-testid={`parse-btn-${d.id}`}
                  className="shrink-0 font-display text-sm border border-graphite text-graphite px-4 py-2 rounded-none hover:bg-graphite hover:text-white transition-colors flex items-center gap-2 disabled:opacity-60">
                  {parsingId === d.id ? <><Loader2 className="h-4 w-4 animate-spin" /> Parsing…</> : <><ScanLine className="h-4 w-4" /> {d.parsed_json ? "Re-parse" : "Parse with AI"}</>}
                </button>
              </div>
            ))}
          </div>
        </TabsContent>

        {/* OPTIMIZE */}
        <TabsContent value="optimize" className="space-y-6">
          <div className="grid lg:grid-cols-2 gap-6">
            <div className="bg-white border border-mist rounded-lg p-6">
              <h3 className="font-display text-lg text-graphite mb-1">Income & deductions</h3>
              <p className="text-sm text-slate-ink mb-5">Edit any value, then recompute.</p>
              <div className="grid sm:grid-cols-2 gap-3">
                {FIELDS.map(([k, label]) => (
                  <label key={k} className="block">
                    <span className="text-xs text-steel font-display">{label}</span>
                    <input type="number" value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })}
                      data-testid={`field-${k}`}
                      className="w-full mt-1 border border-mist rounded-md px-3 py-2 text-sm focus:border-graphite focus:outline-none" />
                  </label>
                ))}
              </div>
              <button onClick={save} disabled={saving} data-testid="recompute-btn"
                className="mt-5 font-display bg-graphite text-white px-5 py-2.5 rounded-none hover:bg-ember transition-colors flex items-center gap-2 disabled:opacity-60">
                {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />} Recompute tax
              </button>
            </div>

            <div className="space-y-6">
              {c && (
                <div className="bg-graphite text-white rounded-lg p-6" data-testid="recommendation-banner">
                  <div className="flex items-center gap-2 text-ember"><TrendingDown className="h-4 w-4" /><span className="text-xs font-display">Recommended</span></div>
                  <div className="font-display text-3xl mt-2">{c.recommended_regime} regime</div>
                  <div className="text-white/70 text-sm mt-1">Saves {inr(c.savings_with_recommended)} vs the alternative.</div>
                  <div className="flex gap-2 mt-4">
                    {["OLD", "NEW"].map((rg) => (
                      <button key={rg} onClick={() => setRegime(rg)} data-testid={`regime-${rg}`}
                        className={`font-display text-sm px-4 py-2 rounded-none transition-colors ${filing.selected_regime === rg ? "bg-white text-graphite" : "border border-white/40 text-white hover:bg-white/10"}`}>
                        {rg} · {inr(rg === "NEW" ? c.tax_liability_new : c.tax_liability_old)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <div className="bg-white border border-mist rounded-lg p-6">
                <h3 className="font-display text-lg text-graphite mb-3">Old vs New liability</h3>
                {c ? <RegimeCompareChart oldTax={c.tax_liability_old} newTax={c.tax_liability_new} /> : <p className="text-slate-ink text-sm py-10 text-center">Recompute to see the comparison.</p>}
              </div>
            </div>
          </div>

          {c && (
            <div className="grid lg:grid-cols-3 gap-6">
              <div className="bg-white border border-mist rounded-lg p-6">
                <h3 className="font-display text-graphite mb-3">Slab utilization · Old</h3>
                <SlabUtilChart slabs={c.slabs_old} color="#202020" />
              </div>
              <div className="bg-white border border-mist rounded-lg p-6">
                <h3 className="font-display text-graphite mb-3">Slab utilization · New</h3>
                <SlabUtilChart slabs={c.slabs_new} color="#ff682c" />
              </div>
              <div className="bg-white border border-mist rounded-lg p-6">
                <h3 className="font-display text-graphite mb-3">Deduction mix</h3>
                <DeductionDonut items={dedItems} />
              </div>
            </div>
          )}
        </TabsContent>

        {/* RECONCILE */}
        <TabsContent value="reconcile" className="space-y-6">
          <div className="bg-ash card-asym p-8">
            <h3 className="font-display text-xl text-graphite">AIS / TIS / 26AS reconciliation</h3>
            <p className="text-steel mt-2 max-w-xl text-sm">Upload your AIS JSON exported from the Income Tax portal (the encrypted utility file, or an already-decrypted JSON). We decrypt it locally and match it against your figures to catch mismatches before a Section 143(1) notice.</p>
            <div className="grid sm:grid-cols-3 gap-3 mt-5 max-w-2xl">
              <label className="block sm:col-span-3">
                <span className="text-xs text-steel font-display">AIS JSON file</span>
                <input type="file" accept=".json,.txt" onChange={(e) => setAisFile(e.target.files[0])} data-testid="ais-file-input"
                  className="w-full mt-1 text-sm file:mr-3 file:border-0 file:bg-graphite file:text-white file:px-3 file:py-2 file:font-display border border-mist bg-white" />
              </label>
              <label className="block">
                <span className="text-xs text-steel font-display">PAN (for decryption)</span>
                <input value={pan} onChange={(e) => setPan(e.target.value.toUpperCase())} placeholder="ABCDE1234F" data-testid="ais-pan"
                  className="w-full mt-1 border border-mist rounded-md px-3 py-2 text-sm focus:border-graphite focus:outline-none" />
              </label>
              <label className="block">
                <span className="text-xs text-steel font-display">DOB (ddmmyyyy)</span>
                <input value={dob} onChange={(e) => setDob(e.target.value)} placeholder="15061990" data-testid="ais-dob"
                  className="w-full mt-1 border border-mist rounded-md px-3 py-2 text-sm focus:border-graphite focus:outline-none" />
              </label>
              <button onClick={uploadAis} disabled={aisBusy} data-testid="upload-ais-btn"
                className="self-end font-display bg-graphite text-white px-5 py-2.5 rounded-none hover:bg-ember transition-colors flex items-center justify-center gap-2 disabled:opacity-60">
                {aisBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />} Decrypt & reconcile
              </button>
            </div>
          </div>
          <div className="space-y-3" data-testid="discrepancies-list">
            {(filing.reconciliation_discrepancies || []).length === 0 ? (
              <div className="flex items-center gap-3 bg-white border border-mist rounded-lg p-5 text-graphite">
                <CheckCircle2 className="h-5 w-5 text-brass" /> No discrepancies recorded. Upload your AIS to verify.
              </div>
            ) : filing.reconciliation_discrepancies.map((f, i) => (
              <div key={i} className={`bg-white border rounded-lg p-5 ${f.severity === "HIGH" ? "border-ember" : "border-mist"}`}>
                <div className="flex items-center gap-2">
                  <AlertTriangle className={`h-4 w-4 ${f.severity === "HIGH" ? "text-ember" : "text-brass"}`} />
                  <span className="font-display text-graphite">{f.field}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full font-display ${f.severity === "HIGH" ? "bg-ember text-white" : "bg-ash text-graphite"}`}>{f.severity}</span>
                </div>
                <p className="text-steel text-sm mt-2">{f.message}</p>
              </div>
            ))}
          </div>
        </TabsContent>

        {/* EXPORT */}
        <TabsContent value="export">
          <div className="grid md:grid-cols-2 gap-4 max-w-3xl">
            <div className="bg-white border border-mist rounded-lg p-8">
              <FileText className="h-6 w-6 text-graphite mb-4" strokeWidth={1.5} />
              <h3 className="font-display text-xl text-graphite">Internal audit package</h3>
              <p className="text-steel mt-2 text-sm">Download the evidence, fact snapshot and deterministic computation package. Official ITD JSON remains disabled until the form-specific schema mapper passes official validation.</p>
              <button onClick={exportJson} data-testid="export-json-btn"
                className="mt-5 font-display bg-graphite text-white px-5 py-2.5 rounded-none hover:bg-ember transition-colors flex items-center gap-2">
                <Download className="h-4 w-4" /> Download audit JSON
              </button>
            </div>
            <div className="bg-ivory card-asym p-8">
              <FileDown className="h-6 w-6 text-graphite mb-4" strokeWidth={1.5} />
              <h3 className="font-display text-xl text-graphite">Computation PDF</h3>
              <p className="text-steel mt-2 text-sm">A clean, client-facing computation summary — income, regime comparison, slab breakup and reconciliation notes.</p>
              <button onClick={downloadPdf} data-testid="download-pdf-btn"
                className="mt-5 font-display bg-graphite text-white px-5 py-2.5 rounded-none hover:bg-ember transition-colors flex items-center gap-2">
                <FileDown className="h-4 w-4" /> Download computation PDF
              </button>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </AppShell>
  );
}
