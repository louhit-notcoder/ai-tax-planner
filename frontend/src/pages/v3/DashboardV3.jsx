import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileWarning, FolderKanban, Plus, Users, LogOut, AlertCircle } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function DashboardV3() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [cases, setCases] = useState([]);
  const [clients, setClients] = useState([]);
  const [summary, setSummary] = useState({});
  const [clientForm, setClientForm] = useState({ display_name: "", email: "", pan: "" });
  const [caseClient, setCaseClient] = useState("");
  const [loadingError, setLoadingError] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const load = async () => {
    console.log("[Dashboard] Loading data...");
    setLoadingError(null);
    setIsLoading(true);
    try {
      const [casesRes, clientsRes, summaryRes] = await Promise.all([
        api.get("/cases"),
        api.get("/clients"),
        api.get("/dashboard")
      ]);
      console.log("[Dashboard] Data loaded:", {
        cases: casesRes.data?.length,
        clients: clientsRes.data?.length
      });
      setCases(casesRes.data || []);
      setClients(clientsRes.data || []);
      setSummary(summaryRes.data || {});
    } catch (error) {
      console.error("[Dashboard] Load error:", error);
      const message = error?.response?.data?.detail || error.message || "Failed to load data";
      setLoadingError(message);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    console.log("[Dashboard] Mounted, calling load()");
    load();
  }, []);

  const createClient = async () => {
    try {
      await api.post("/clients", {
        ...clientForm,
        email: clientForm.email || null,
        pan: clientForm.pan || null
      });
      setClientForm({ display_name: "", email: "", pan: "" });
      await load();
    } catch (error) {
      console.error("[Dashboard] Create client error:", error);
      setLoadingError(error.response?.data?.detail || "Failed to create client");
    }
  };

  const createCase = async () => {
    try {
      const { data } = await api.post("/cases", {
        client_id: caseClient,
        tax_period: "FY 2025-26",
        assessment_year: "AY 2026-27",
        selected_regime: "NEW"
      });
      navigate(`/cases/${data.id}`);
    } catch (error) {
      console.error("[Dashboard] Create case error:", error);
      setLoadingError(error.response?.data?.detail || "Failed to create case");
    }
  };

  const handleLogout = async () => {
    console.log("[Dashboard] Logging out...");
    await logout();
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-600 mx-auto mb-4"></div>
          <p className="text-slate-600">Loading your workspace...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-white border-b px-6 py-4 flex justify-between">
        <div>
          <h1 className="font-display text-2xl">Green Papaya CA Workspace</h1>
          <p className="text-sm text-slate-500">
            {user?.role} · {user?.email} · tenant {user?.tenant_id}
          </p>
        </div>
        <Button variant="outline" onClick={handleLogout}>
          <LogOut className="h-4 w-4 mr-2" />Sign out
        </Button>
      </header>

      <main className="p-6 max-w-7xl mx-auto space-y-6">
        {loadingError && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-center gap-3">
            <AlertCircle className="h-5 w-5 text-red-600" />
            <div>
              <p className="text-red-800 font-medium">Error</p>
              <p className="text-red-600 text-sm">{loadingError}</p>
            </div>
            <Button variant="outline" size="sm" onClick={load} className="ml-auto">
              Retry
            </Button>
          </div>
        )}

        <div className="grid md:grid-cols-4 gap-4">
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-blue-100 rounded-lg"><FolderKanban className="h-6 w-6 text-blue-600" /></div>
                <div><p className="text-2xl font-bold">{cases.length}</p><p className="text-sm text-slate-500">Tax Cases</p></div>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-green-100 rounded-lg"><Users className="h-6 w-6 text-green-600" /></div>
                <div><p className="text-2xl font-bold">{clients.length}</p><p className="text-sm text-slate-500">Clients</p></div>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="grid md:grid-cols-2 gap-6">
          <Card>
            <CardHeader><CardTitle>Add Client</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <Input placeholder="Client name" value={clientForm.display_name} onChange={e => setClientForm(f => ({ ...f, display_name: e.target.value }))} />
              <Input placeholder="Email (optional)" type="email" value={clientForm.email} onChange={e => setClientForm(f => ({ ...f, email: e.target.value }))} />
              <Input placeholder="PAN (optional)" value={clientForm.pan} onChange={e => setClientForm(f => ({ ...f, pan: e.target.value }))} />
              <Button onClick={createClient} className="w-full"><Plus className="h-4 w-4 mr-2" />Add Client</Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>New Tax Case</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <select className="w-full p-2 border rounded-md" value={caseClient} onChange={e => setCaseClient(e.target.value)}>
                <option value="">Select client...</option>
                {clients.map(c => <option key={c.id} value={c.id}>{c.display_name}</option>)}
              </select>
              <div className="text-sm text-slate-500">FY 2025-26 · AY 2026-27 · New Regime</div>
              <Button onClick={createCase} disabled={!caseClient} className="w-full"><Plus className="h-4 w-4 mr-2" />Create Case</Button>
            </CardContent>
          </Card>
        </div>

        {cases.length > 0 && (
          <Card>
            <CardHeader><CardTitle>Recent Cases</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-2">
                {cases.slice(0, 5).map(c => (
                  <div key={c.id} className="flex justify-between items-center p-3 bg-slate-50 rounded-lg cursor-pointer hover:bg-slate-100" onClick={() => navigate(`/cases/${c.id}`)}>
                    <div><p className="font-medium">{c.client_name}</p><p className="text-sm text-slate-500">{c.assessment_year} · {c.status}</p></div>
                    <span className="text-sm text-slate-400">→</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
