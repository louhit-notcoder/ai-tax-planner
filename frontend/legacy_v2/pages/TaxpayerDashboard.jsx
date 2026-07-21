import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppShell from "@/components/AppShell";
import { inr, STATUS_LABELS } from "@/lib/format";
import { Plus, FileText, ArrowRight, ShieldCheck, TrendingDown, Layers } from "lucide-react";
import { toast } from "sonner";

const links = [{ to: "/dashboard", label: "My Filings" }];

const badge = (s) => {
  const map = {
    reconciled: "bg-ivory text-brass", json_generated: "bg-graphite text-white",
    completed: "bg-graphite text-white", under_review: "bg-ash text-graphite",
    not_started: "bg-fog text-slate-ink",
  };
  return map[s] || "bg-fog text-slate-ink";
};

const Stat = ({ icon: Icon, label, value, tone }) => (
  <div className="bg-white border border-mist rounded-lg p-6">
    <div className="flex items-center justify-between">
      <span className="text-sm text-slate-ink font-display">{label}</span>
      <Icon className={`h-4 w-4 ${tone || "text-brass"}`} strokeWidth={1.5} />
    </div>
    <div className="font-display text-3xl text-graphite mt-3">{value}</div>
  </div>
);

export default function TaxpayerDashboard() {
  const [filings, setFilings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const navigate = useNavigate();

  const load = async () => {
    try { const r = await api.get("/filings"); setFilings(r.data); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    setCreating(true);
    try {
      const r = await api.post("/filings", { assessment_year: "AY 2026-27" });
      navigate(`/filing/${r.data.id}`);
    } catch { toast.error("Could not create filing"); setCreating(false); }
  };

  const best = filings.reduce((acc, f) => {
    const c = f.tax_computation_summary;
    return acc + (c ? c.savings_with_recommended : 0);
  }, 0);
  const active = filings.filter((f) => !["completed", "json_generated"].includes(f.status)).length;

  return (
    <AppShell links={links}>
      <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div>
          <p className="text-brass font-display text-sm">AY 2026-27 · FY 2025-26</p>
          <h1 className="heading-lg text-graphite mt-1">Your tax workspace</h1>
        </div>
        <button onClick={create} disabled={creating} data-testid="new-filing-btn"
          className="font-display text-[15px] bg-graphite text-white px-5 py-3 rounded-none hover:bg-ember transition-colors flex items-center gap-2 disabled:opacity-60">
          <Plus className="h-4 w-4" /> {creating ? "Creating…" : "New filing"}
        </button>
      </div>

      <div className="grid sm:grid-cols-3 gap-4 mb-10">
        <Stat icon={Layers} label="Total filings" value={filings.length} />
        <Stat icon={FileText} label="Active returns" value={active} />
        <Stat icon={TrendingDown} label="Potential savings" value={inr(best)} tone="text-ember" />
      </div>

      {loading ? (
        <div className="text-slate-ink">Loading filings…</div>
      ) : filings.length === 0 ? (
        <div className="bg-ash card-asym p-14 text-center" data-testid="empty-filings">
          <div className="h-14 w-14 mx-auto bg-white border border-mist flex items-center justify-center">
            <ShieldCheck className="h-6 w-6 text-graphite" strokeWidth={1.5} />
          </div>
          <h3 className="font-display text-2xl text-graphite mt-6">Start your first return</h3>
          <p className="text-steel mt-2 max-w-md mx-auto">Create a filing, upload your Form 16 and let the parser + regime sandbox do the heavy lifting.</p>
          <button onClick={create} className="mt-6 font-display bg-graphite text-white px-6 py-3 rounded-none hover:bg-ember transition-colors">Create filing</button>
        </div>
      ) : (
        <div className="grid md:grid-cols-2 gap-4" data-testid="filings-list">
          {filings.map((f) => {
            const c = f.tax_computation_summary;
            const tax = c ? (f.selected_regime === "NEW" ? c.tax_liability_new : c.tax_liability_old) : null;
            return (
              <button key={f.id} onClick={() => navigate(`/filing/${f.id}`)} data-testid={`filing-card-${f.id}`}
                className="text-left bg-white border border-mist rounded-lg p-6 hover:border-graphite transition-colors group">
                <div className="flex items-center justify-between">
                  <span className="font-display text-graphite">{f.assessment_year}</span>
                  <span className={`text-xs px-2.5 py-1 rounded-full font-display ${badge(f.status)}`}>{STATUS_LABELS[f.status]}</span>
                </div>
                <div className="flex items-center gap-6 mt-5">
                  <div>
                    <div className="text-xs text-slate-ink">Suggested form</div>
                    <div className="font-display text-lg text-graphite">{f.selected_itr_form}</div>
                  </div>
                  <div>
                    <div className="text-xs text-slate-ink">Tax liability ({f.selected_regime})</div>
                    <div className="font-display text-lg text-graphite">{tax !== null ? inr(tax) : "—"}</div>
                  </div>
                </div>
                <span className="inline-flex items-center gap-2 mt-5 text-sm font-display text-graphite group-hover:text-ember transition-colors">
                  Open workspace <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
                </span>
              </button>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
