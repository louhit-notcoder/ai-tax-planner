import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Users, FileText, ArrowRight, LogOut, Briefcase, ChevronRight } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export default function DashboardV3() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [clients, setClients] = useState([]);
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showNewClient, setShowNewClient] = useState(false);
  const [selectedClient, setSelectedClient] = useState(null);
  const [clientForm, setClientForm] = useState({ display_name: "", email: "", pan: "" });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [casesRes, clientsRes] = await Promise.all([
        api.get("/cases"),
        api.get("/clients"),
      ]);
      setCases(casesRes.data || []);
      setClients(clientsRes.data || []);
    } catch (err) {
      console.error("Failed to load:", err);
    } finally {
      setLoading(false);
    }
  };

  const getClientCases = (clientId) => {
    return cases.filter((c) => c.client_id === clientId || c.clientId === clientId);
  };

  const createClient = async () => {
    if (!clientForm.display_name.trim()) return;
    setCreating(true);
    try {
      const { data: clientData } = await api.post("/clients", {
        display_name: clientForm.display_name,
        email: clientForm.email || null,
        pan: clientForm.pan || null,
      });

      // Create a case for the new client
      await api.post("/cases", {
        client_id: clientData.id,
        tax_period: "FY 2025-26",
        assessment_year: "AY 2026-27",
        selected_regime: "NEW",
      });

      setClientForm({ display_name: "", email: "", pan: "" });
      setShowNewClient(false);
      await loadData();
    } catch (err) {
      console.error("Failed to create client:", err);
    } finally {
      setCreating(false);
    }
  };

  const createCase = async (clientId) => {
    try {
      const { data } = await api.post("/cases", {
        client_id: clientId,
        tax_period: "FY 2025-26",
        assessment_year: "AY 2026-27",
        selected_regime: "NEW",
      });
      navigate(`/cases/${data.id}`);
    } catch (err) {
      console.error("Failed to create case:", err);
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return "No activity";
    const date = new Date(dateString);
    const now = new Date();
    const diffTime = Math.abs(now - date);
    const diffDays = Math.floor(diffTime / (1000 * 60 * 60 * 24));

    if (diffDays === 0) return "Today";
    if (diffDays === 1) return "Yesterday";
    if (diffDays < 7) return `${diffDays} days ago`;
    return date.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-50">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 bg-gradient-to-br from-emerald-500 to-teal-600 rounded-lg flex items-center justify-center">
              <Briefcase className="w-4 h-4 text-white" />
            </div>
            <span className="text-gray-900 font-semibold text-lg">Green Papaya</span>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-500">{user?.email}</span>
            <Button
              variant="ghost"
              size="sm"
              onClick={logout}
              className="text-gray-400 hover:text-gray-600"
            >
              <LogOut className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-5xl mx-auto px-6 py-10">
        {selectedClient ? (
          /* Cases View */
          <div>
            <button
              onClick={() => setSelectedClient(null)}
              className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 mb-6 transition-colors"
            >
              <ArrowRight className="w-4 h-4 rotate-180" />
              Back to clients
            </button>

            <div className="flex items-center justify-between mb-8">
              <div>
                <h1 className="text-2xl font-semibold text-gray-900">{selectedClient.display_name}</h1>
                <p className="text-gray-500 mt-1">
                  {getClientCases(selectedClient.id).length} case{getClientCases(selectedClient.id).length !== 1 ? "s" : ""}
                </p>
              </div>
              <Button
                onClick={() => createCase(selectedClient.id)}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                <Plus className="w-4 h-4 mr-2" />
                New Case
              </Button>
            </div>

            {getClientCases(selectedClient.id).length === 0 ? (
              <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
                <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No cases yet</h3>
                <p className="text-gray-500 mb-6">Create a new case to start working on this client's taxes</p>
                <Button
                  onClick={() => createCase(selectedClient.id)}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Create First Case
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {getClientCases(selectedClient.id).map((c) => (
                  <button
                    key={c.id}
                    onClick={() => navigate(`/cases/${c.id}`)}
                    className="w-full bg-white rounded-xl border border-gray-200 p-5 hover:border-emerald-300 hover:shadow-sm transition-all flex items-center justify-between group"
                  >
                    <div className="flex items-center gap-4">
                      <div className="w-10 h-10 bg-emerald-50 rounded-lg flex items-center justify-center">
                        <FileText className="w-5 h-5 text-emerald-600" />
                      </div>
                      <div className="text-left">
                        <h3 className="font-medium text-gray-900">
                          {c.tax_period || "Tax Filing"} · {c.assessment_year || "AY 2026-27"}
                        </h3>
                        <p className="text-sm text-gray-500">
                          {c.regime || "New Regime"} · {c.document_count || 0} documents
                        </p>
                      </div>
                    </div>
                    <ChevronRight className="w-5 h-5 text-gray-400 group-hover:text-emerald-600 transition-colors" />
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          /* Clients View */
          <div>
            <div className="flex items-center justify-between mb-8">
              <div>
                <h1 className="text-2xl font-semibold text-gray-900">Your Clients</h1>
                <p className="text-gray-500 mt-1">Manage and work on client tax cases</p>
              </div>
              <Button
                onClick={() => setShowNewClient(true)}
                className="bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                <Plus className="w-4 h-4 mr-2" />
                New Client
              </Button>
            </div>

            {loading ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {[1, 2, 3, 4, 5, 6].map((i) => (
                  <div key={i} className="bg-white rounded-xl border border-gray-200 p-5 animate-pulse">
                    <div className="flex items-start gap-4">
                      <div className="w-10 h-10 bg-gray-200 rounded-lg" />
                      <div className="flex-1">
                        <div className="h-4 bg-gray-200 rounded w-2/3 mb-2" />
                        <div className="h-3 bg-gray-100 rounded w-1/2" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : clients.length === 0 ? (
              <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
                <Users className="w-12 h-12 text-gray-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-gray-900 mb-2">No clients yet</h3>
                <p className="text-gray-500 mb-6">Add your first client to start preparing their tax return</p>
                <Button
                  onClick={() => setShowNewClient(true)}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white"
                >
                  <Plus className="w-4 h-4 mr-2" />
                  Add First Client
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {clients.map((client) => {
                  const clientCases = getClientCases(client.id);
                  const lastCase = clientCases[0];
                  const lastActivity = lastCase?.updated_at || client.created_at;

                  return (
                    <button
                      key={client.id}
                      onClick={() => setSelectedClient(client)}
                      className="bg-white rounded-xl border border-gray-200 p-5 hover:border-emerald-300 hover:shadow-md transition-all text-left group"
                    >
                      <div className="flex items-start gap-4">
                        <div className="w-10 h-10 bg-gradient-to-br from-blue-500 to-indigo-600 rounded-lg flex items-center justify-center shrink-0">
                          <Users className="w-5 h-5 text-white" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <h3 className="font-medium text-gray-900 truncate">{client.display_name}</h3>
                          <p className="text-sm text-gray-500 mt-1">
                            {clientCases.length} case{clientCases.length !== 1 ? "s" : ""}
                          </p>
                          {lastActivity && (
                            <p className="text-xs text-gray-400 mt-1">
                              Last activity: {formatDate(lastActivity)}
                            </p>
                          )}
                        </div>
                      </div>
                      <div className="mt-4 pt-3 border-t border-gray-100 flex items-center justify-between">
                        <span className="text-xs text-gray-400">View cases</span>
                        <ArrowRight className="w-4 h-4 text-gray-400 group-hover:text-emerald-600 group-hover:translate-x-1 transition-all" />
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </main>

      {/* New Client Modal */}
      {showNewClient && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl shadow-xl p-6 w-full max-w-md">
            <h2 className="text-xl font-semibold text-gray-900 mb-1">Add New Client</h2>
            <p className="text-sm text-gray-500 mb-6">Create a client and their first tax case</p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Client Name <span className="text-red-500">*</span>
                </label>
                <Input
                  placeholder="Enter client name"
                  value={clientForm.display_name}
                  onChange={(e) => setClientForm({ ...clientForm, display_name: e.target.value })}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  Email
                </label>
                <Input
                  type="email"
                  placeholder="client@email.com"
                  value={clientForm.email}
                  onChange={(e) => setClientForm({ ...clientForm, email: e.target.value })}
                  className="w-full"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  PAN Number
                </label>
                <Input
                  placeholder="ABCDE1234F"
                  value={clientForm.pan}
                  onChange={(e) => setClientForm({ ...clientForm, pan: e.target.value.toUpperCase() })}
                  className="w-full font-mono"
                  maxLength={10}
                />
              </div>
            </div>

            <div className="flex gap-3 mt-6">
              <Button
                variant="outline"
                onClick={() => {
                  setShowNewClient(false);
                  setClientForm({ display_name: "", email: "", pan: "" });
                }}
                className="flex-1"
              >
                Cancel
              </Button>
              <Button
                onClick={createClient}
                disabled={creating || !clientForm.display_name.trim()}
                className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
              >
                {creating ? "Creating..." : "Add Client"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
