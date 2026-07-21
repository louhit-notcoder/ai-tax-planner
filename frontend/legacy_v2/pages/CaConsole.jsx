import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import AppShell from "@/components/AppShell";
import { inr, STATUS_LABELS } from "@/lib/format";
import { toast } from "sonner";
import {
  Users, FileWarning, CheckCircle2, Clock, UserPlus, ArrowRight,
  AlertTriangle, MessageCircle,
} from "lucide-react";

const links = [
  { to: "/ca", label: "Dashboard" },
  { to: "/ca/audit", label: "Audit Trails" },
];

const Stat = ({ icon: Icon, label, value, tone }) => (
  <div className="bg-white border border-mist rounded-lg p-6">
    <div className="flex items-center justify-between">
      <span className="text-sm text-slate-ink font-display">{label}</span>
      <Icon className={`h-4 w-4 ${tone || "text-brass"}`} strokeWidth={1.5} />
    </div>
    <div className="font-display text-3xl text-graphite mt-3">{value}</div>
  </div>
);

const actionFor = (f) => {
  if ((f.reconciliation_discrepancies || []).length) return { label: "Resolve Alert", alert: true };
  if (f.status === "under_review") return { label: "Open Desk" };
  if (f.status === "reconciled") return { label: "Compile JSON" };
  return { label: "Open Desk" };
};

export default function CaConsole() {
  const [stats, setStats] = useState(null);
  const [triage, setTriage] = useState([]);
  const [queue, setQueue] = useState([]);
  const [email, setEmail] = useState("");
  const [linking, setLinking] = useState(false);
  const navigate = useNavigate();

  const load = async () => {
    const [s, t, q] = await Promise.all([
      api.get("/ca/stats"), api.get("/ca/triage"), api.get("/whatsapp/queue").catch(() => ({ data: [] })),
    ]);
    setStats(s.data); setTriage(t.data); setQueue(q.data);
  };
  useEffect(() => { load(); }, []);

  const link = async () => {
    if (!email.trim()) return;
    setLinking(true);
    try {
      await api.post("/ca/link-client", { client_email: email.trim() });
      toast.success(`Linked ${email}`);
      setEmail(""); load();
    } catch (e) { toast.error(e.response?.data?.detail || "Could not link client"); }
    finally { setLinking(false); }
  };

  return (
    <AppShell links={links}>
      <div className="flex flex-wrap items-end justify-between gap-4 mb-8">
        <div>
          <p className="text-brass font-display text-sm">Firm control console · AY 2026-27</p>
          <h1 className="heading-lg text-graphite mt-1">Client filing triage</h1>
        </div>
        <div className="flex items-center gap-2">
          <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="taxpayer@email.com"
            data-testid="link-client-input"
            className="border border-mist rounded-none px-3 py-2.5 text-sm w-56 focus:border-graphite focus:outline-none" />
          <button onClick={link} disabled={linking} data-testid="link-client-btn"
            className="font-display text-[15px] bg-graphite text-white px-4 py-2.5 rounded-none hover:bg-ember transition-colors flex items-center gap-2 disabled:opacity-60">
            <UserPlus className="h-4 w-4" /> Link client
          </button>
        </div>
      </div>

      {stats && (
        <div className="grid sm:grid-cols-4 gap-4 mb-10">
          <Stat icon={Users} label="Clients" value={stats.clients} />
          <Stat icon={Clock} label="Awaiting review" value={stats.awaiting_review} />
          <Stat icon={FileWarning} label="Open mismatches" value={stats.open_mismatches} tone="text-ember" />
          <Stat icon={CheckCircle2} label="Compiled" value={stats.completed} />
        </div>
      )}

      <div className="bg-white border border-mist rounded-lg overflow-hidden mb-10">
        <div className="grid grid-cols-12 px-6 py-4 border-b border-mist bg-fog text-xs font-display text-slate-ink uppercase tracking-wide">
          <div className="col-span-3">Client</div>
          <div className="col-span-2">Income heads</div>
          <div className="col-span-2">ITR form</div>
          <div className="col-span-3">Compliance status</div>
          <div className="col-span-2 text-right">Action</div>
        </div>
        {triage.length === 0 ? (
          <div className="px-6 py-10 text-center text-slate-ink" data-testid="empty-triage">
            No client filings assigned yet. Link a taxpayer by email to begin.
          </div>
        ) : triage.map((f) => {
          const a = actionFor(f);
          const p = f.parsed_payload || {};
          const heads = [p.gross_salary ? "Salary" : null, (p.stcg_equity || p.ltcg_equity) ? "CG" : null, p.house_property_income ? "HP" : null].filter(Boolean).join(", ") || "—";
          return (
            <div key={f.id} className="grid grid-cols-12 px-6 py-4 border-b border-mist items-center hover:bg-fog transition-colors" data-testid={`triage-row-${f.id}`}>
              <div className="col-span-3">
                <div className="font-display text-graphite">{f.user_name}</div>
                <div className="text-xs text-slate-ink truncate">{f.user_email}</div>
              </div>
              <div className="col-span-2 text-sm text-steel">{heads}</div>
              <div className="col-span-2 font-display text-graphite">{f.selected_itr_form}</div>
              <div className="col-span-3">
                <span className="inline-flex items-center gap-1.5 text-sm text-graphite">
                  {(f.reconciliation_discrepancies || []).length ? <AlertTriangle className="h-3.5 w-3.5 text-ember" /> : null}
                  {STATUS_LABELS[f.status]}
                </span>
              </div>
              <div className="col-span-2 flex justify-end">
                <button onClick={() => navigate(`/ca/desk/${f.id}`)} data-testid={`open-desk-${f.id}`}
                  className={`font-display text-sm px-4 py-2 rounded-none flex items-center gap-1.5 transition-colors ${a.alert ? "bg-ember text-white hover:bg-graphite" : "border border-graphite text-graphite hover:bg-graphite hover:text-white"}`}>
                  {a.label} <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <div className="bg-ash card-asym p-8">
        <div className="flex items-center gap-2 mb-4"><MessageCircle className="h-5 w-5 text-graphite" /><h3 className="font-display text-xl text-graphite">WhatsApp intake queue</h3></div>
        {queue.length === 0 ? (
          <p className="text-steel text-sm">No WhatsApp documents yet. The webhook is live at <code className="text-brass">/api/v1/integrations/whatsapp</code> — connect Twilio to activate real ingest.</p>
        ) : (
          <div className="space-y-2" data-testid="whatsapp-queue">
            {queue.map((q) => (
              <div key={q.id} className="bg-white rounded-md px-4 py-3 flex items-center justify-between text-sm">
                <span className="font-display text-graphite">{q.sender_phone}</span>
                <span className="text-slate-ink">{q.status}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  );
}
