import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { FileWarning, FolderKanban, Plus, Users, LogOut } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function DashboardV3() {
  const { user, logout } = useAuth(); const navigate = useNavigate();
  const [cases, setCases] = useState([]); const [clients, setClients] = useState([]); const [summary, setSummary] = useState({});
  const [clientForm, setClientForm] = useState({ display_name: "", email: "", pan: "" }); const [caseClient, setCaseClient] = useState("");
  const load = async () => { const [a,b,c] = await Promise.all([api.get("/cases"), api.get("/clients"), api.get("/dashboard")]); setCases(a.data); setClients(b.data); setSummary(c.data); };
  useEffect(() => { load().catch(console.error); }, []);
  const createClient = async () => { await api.post("/clients", { ...clientForm, email: clientForm.email || null, pan: clientForm.pan || null }); setClientForm({display_name:"",email:"",pan:""}); await load(); };
  const createCase = async () => { const { data } = await api.post("/cases", { client_id: caseClient, tax_period: "FY 2025-26", assessment_year: "AY 2026-27", selected_regime: "NEW" }); navigate(`/cases/${data.id}`); };
  return <div className="min-h-screen bg-slate-50">
    <header className="bg-white border-b px-6 py-4 flex justify-between"><div><h1 className="font-display text-2xl">Green Papaya CA Workspace</h1><p className="text-sm text-slate-500">{user?.role} · tenant {user?.tenant_id}</p></div><Button variant="outline" onClick={logout}><LogOut className="h-4 w-4 mr-2"/>Sign out</Button></header>
    <main className="p-6 max-w-7xl mx-auto space-y-6">
      <div className="grid md:grid-cols-4 gap-4">
        <Stat icon={FolderKanban} label="Cases" value={cases.length}/><Stat icon={Users} label="Clients" value={clients.length}/><Stat icon={FileWarning} label="Open missing items" value={summary.open_missing_items || 0}/><Stat icon={FileWarning} label="Discrepancies" value={summary.unresolved_discrepancies || 0}/>
      </div>
      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2"><CardHeader><CardTitle>Client tax cases</CardTitle></CardHeader><CardContent className="space-y-2">{cases.map((item) => <button key={item.id} onClick={() => navigate(`/cases/${item.id}`)} className="w-full text-left p-4 rounded-lg border bg-white hover:border-slate-400 flex justify-between"><div><div className="font-medium">{item.client_name}</div><div className="text-sm text-slate-500">{item.tax_period} · {item.assessment_year}</div></div><div className="text-sm font-medium">{item.status}</div></button>)}{!cases.length && <p className="text-slate-500">No cases yet.</p>}</CardContent></Card>
        <div className="space-y-6"><Card><CardHeader><CardTitle className="text-lg">Add client</CardTitle></CardHeader><CardContent className="space-y-3"><Input placeholder="Client name" value={clientForm.display_name} onChange={e=>setClientForm({...clientForm,display_name:e.target.value})}/><Input placeholder="Email" value={clientForm.email} onChange={e=>setClientForm({...clientForm,email:e.target.value})}/><Input placeholder="PAN" value={clientForm.pan} onChange={e=>setClientForm({...clientForm,pan:e.target.value.toUpperCase()})}/><Button onClick={createClient}><Plus className="h-4 w-4 mr-2"/>Create client</Button></CardContent></Card>
        <Card><CardHeader><CardTitle className="text-lg">Start AY 2026–27 case</CardTitle></CardHeader><CardContent className="space-y-3"><select className="w-full h-10 border rounded-md px-3" value={caseClient} onChange={e=>setCaseClient(e.target.value)}><option value="">Select client</option>{clients.map(c=><option key={c.id} value={c.id}>{c.display_name}</option>)}</select><Button disabled={!caseClient} onClick={createCase}>Create case</Button></CardContent></Card></div>
      </div>
    </main>
  </div>;
}
function Stat({icon:Icon,label,value}) { return <Card><CardContent className="p-5 flex items-center gap-4"><Icon className="h-7 w-7 text-slate-600"/><div><div className="text-2xl font-semibold">{value}</div><div className="text-xs text-slate-500">{label}</div></div></CardContent></Card> }
