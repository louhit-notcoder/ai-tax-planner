import { useEffect, useState } from "react";
import api from "@/lib/api";
import AppShell from "@/components/AppShell";
import { ShieldCheck, Clock } from "lucide-react";

const links = [{ to: "/ca", label: "Dashboard" }, { to: "/ca/audit", label: "Audit Trails" }];

export default function AuditTrails() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/ca/audit-logs").then((r) => setLogs(r.data)).finally(() => setLoading(false));
  }, []);

  return (
    <AppShell links={links}>
      <div className="flex items-center gap-3 mb-2">
        <ShieldCheck className="h-6 w-6 text-graphite" strokeWidth={1.5} />
        <h1 className="heading-lg text-graphite">Immutable audit trails</h1>
      </div>
      <p className="text-steel mb-8 max-w-xl">Every field override and document access is recorded with a mandatory justification — a defensible record for ICAI peer review.</p>

      {loading ? <div className="text-slate-ink">Loading…</div> : logs.length === 0 ? (
        <div className="bg-ash card-asym p-14 text-center" data-testid="empty-audit">
          <p className="text-steel">No audit events recorded yet. Overrides on the client desk will appear here.</p>
        </div>
      ) : (
        <div className="bg-white border border-mist rounded-lg overflow-hidden" data-testid="audit-table">
          {logs.map((l, i) => (
            <div key={l.id} className={`px-6 py-4 flex items-start gap-4 ${i < logs.length - 1 ? "border-b border-mist" : ""}`}>
              <div className="h-9 w-9 bg-ash flex items-center justify-center shrink-0 mt-0.5">
                <Clock className="h-4 w-4 text-graphite" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-display text-graphite">{l.modified_field}</span>
                  {l.previous_value !== null && l.previous_value !== undefined && (
                    <span className="text-sm text-slate-ink">{l.previous_value} → <span className="text-ember">{l.new_value}</span></span>
                  )}
                  <span className="text-xs text-brass font-display ml-auto">{new Date(l.timestamp).toLocaleString("en-IN")}</span>
                </div>
                {l.justification && <p className="text-steel text-sm mt-1">"{l.justification}"</p>}
                {l.operator_name && <p className="text-xs text-slate-ink mt-1">by {l.operator_name}</p>}
              </div>
            </div>
          ))}
        </div>
      )}
    </AppShell>
  );
}
