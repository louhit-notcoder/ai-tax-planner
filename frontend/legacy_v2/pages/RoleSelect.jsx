import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { User, Briefcase, ArrowRight, LockKeyhole } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Logo } from "@/components/Logo";
import { toast } from "sonner";

export default function RoleSelect() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const [busy, setBusy] = useState(false);

  const continueAsTaxpayer = async () => {
    setBusy(true);
    try {
      const res = await api.post("/auth/role", { role: "taxpayer" });
      setUser(res.data);
      navigate("/dashboard");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not set up the taxpayer workspace.");
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <header className="max-w-[1200px] mx-auto px-6 py-6"><Logo /></header>
      <main className="max-w-[1000px] mx-auto px-6 pt-10 pb-24">
        <p className="text-brass font-display text-sm">Welcome to Green Papaya</p>
        <h1 className="display-xl text-graphite mt-3 max-w-2xl">Choose your workspace</h1>
        <p className="text-steel text-lg mt-4 max-w-xl">Taxpayer access is self-service. CA firm roles are invitation-only to protect client data.</p>
        <div className="grid md:grid-cols-2 gap-5 mt-12">
          <button data-testid="role-taxpayer" onClick={continueAsTaxpayer} disabled={busy}
            className="text-left bg-ash card-asym p-10 transition-all duration-300 hover:bg-ivory disabled:opacity-60 rise group">
            <div className="h-12 w-12 flex items-center justify-center bg-white border border-mist"><User className="h-6 w-6 text-graphite" strokeWidth={1.5} /></div>
            <h2 className="font-display text-2xl text-graphite mt-8">I am a taxpayer</h2>
            <p className="text-steel mt-3 leading-relaxed">Upload documents, review provisional calculations and submit the case to an invited CA.</p>
            <span className="inline-flex items-center gap-2 mt-8 font-display text-graphite">{busy ? "Setting up…" : "Continue"}<ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" /></span>
          </button>
          <div className="text-left bg-white border border-mist card-asym p-10 rise d2">
            <div className="h-12 w-12 flex items-center justify-center bg-ash border border-mist"><Briefcase className="h-6 w-6 text-graphite" strokeWidth={1.5} /></div>
            <h2 className="font-display text-2xl text-graphite mt-8">I work at a CA firm</h2>
            <p className="text-steel mt-3 leading-relaxed">Firm access requires an invitation from a firm owner or authorised reviewer. This prevents self-service privilege escalation.</p>
            <span className="inline-flex items-center gap-2 mt-8 font-display text-brass"><LockKeyhole className="h-4 w-4" /> Invitation required</span>
          </div>
        </div>
      </main>
    </div>
  );
}
