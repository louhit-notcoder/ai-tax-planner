import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { ShieldCheck, Calculator } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginV3() {
  const { user, establishSession } = useAuth();
  const [invitationToken] = useState(() => new URLSearchParams(window.location.search).get("invitation"));
  const [mode, setMode] = useState(invitationToken ? "invitation" : "login");
  useEffect(() => { if (invitationToken) window.history.replaceState({}, "", window.location.pathname); }, [invitationToken]);
  const [form, setForm] = useState({ email: "", password: "", tenant_slug: "", totp_code: "", firm_name: "", firm_slug: "", owner_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/dashboard" replace />;

  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const endpoint = mode === "bootstrap" ? "/auth/bootstrap" : mode === "invitation" ? "/auth/invitations/accept" : "/auth/login";
      const payload = mode === "bootstrap" ? {
        firm_name: form.firm_name, firm_slug: form.firm_slug, owner_name: form.owner_name,
        owner_email: form.email, password: form.password,
      } : mode === "invitation" ? { token: invitationToken, full_name: form.owner_name, password: form.password } : { email: form.email, password: form.password, tenant_slug: form.tenant_slug || null, totp_code: form.totp_code || null };
      const { data } = await api.post(endpoint, payload);
      if (data.tenant_selection_required) throw new Error("Enter the firm slug for the tenant you want to access.");
      establishSession(data);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || "Unable to sign in");
    } finally { setBusy(false); }
  };

  const update = (key) => (e) => setForm((current) => ({ ...current, [key]: e.target.value }));
  return <div className="min-h-screen bg-slate-50 grid lg:grid-cols-2">
    <div className="hidden lg:flex p-16 bg-slate-950 text-white flex-col justify-between">
      <div className="flex gap-3 items-center"><Calculator className="h-8 w-8"/><span className="font-display text-2xl">Green Papaya</span></div>
      <div><h1 className="text-5xl font-semibold leading-tight">Evidence-linked tax preparation for CA firms.</h1><p className="mt-6 text-slate-300 text-lg">Deterministic computation, maker-checker review, secure documents and controlled AI assistance.</p></div>
      <div className="flex items-center gap-2 text-sm text-slate-300"><ShieldCheck className="h-5 w-5"/>Every material number remains reviewable and reproducible.</div>
    </div>
    <div className="flex items-center justify-center p-6">
      <Card className="w-full max-w-md"><CardHeader><CardTitle>{mode === "bootstrap" ? "Create development firm" : mode === "invitation" ? "Accept firm invitation" : "Sign in to your firm"}</CardTitle></CardHeader><CardContent>
        <form className="space-y-4" onSubmit={submit}>
          {mode === "bootstrap" && <><Input placeholder="Firm name" value={form.firm_name} onChange={update("firm_name")}/><Input placeholder="Firm slug (example-ca)" value={form.firm_slug} onChange={update("firm_slug")}/><Input placeholder="Owner full name" value={form.owner_name} onChange={update("owner_name")}/></>}
          {mode === "invitation" && <Input placeholder="Your full name" value={form.owner_name} onChange={update("owner_name")} required />}
          {mode !== "invitation" && <Input type="email" placeholder="Email" value={form.email} onChange={update("email")} required />}
          <Input type="password" placeholder="Password" value={form.password} onChange={update("password")} required />
          {mode === "login" && <><Input placeholder="Firm slug (when you belong to multiple firms)" value={form.tenant_slug} onChange={update("tenant_slug")}/><Input placeholder="6-digit MFA code" value={form.totp_code} onChange={update("totp_code")}/></>}
          {error && <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">{typeof error === "string" ? error : JSON.stringify(error)}</div>}
          <Button className="w-full" disabled={busy}>{busy ? "Please wait…" : mode === "bootstrap" ? "Create firm" : mode === "invitation" ? "Accept invitation" : "Sign in"}</Button>
        </form>
        {!invitationToken && <button className="mt-4 text-sm underline text-slate-600" onClick={() => setMode(mode === "login" ? "bootstrap" : "login")}>{mode === "login" ? "First local setup? Create a development firm" : "Already configured? Sign in"}</button>}
      </CardContent></Card>
    </div>
  </div>;
}
