import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { ShieldCheck } from "lucide-react";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

export default function MfaSetupV3() {
  const { user, establishSession } = useAuth();
  const [setup, setSetup] = useState(null); const [code, setCode] = useState(""); const [error, setError] = useState("");
  useEffect(() => { if (user && !user.mfa_enabled) api.post("/auth/mfa/setup").then(({data})=>setSetup(data)).catch((e)=>setError(e.response?.data?.detail||e.message)); }, [user]);
  if (!user) return <Navigate to="/" replace/>;
  if (user.mfa_enabled && user.mfa_verified) return <Navigate to="/dashboard" replace/>;
  const confirm=async()=>{try{const{data}=await api.post("/auth/mfa/confirm",{code});establishSession(data);}catch(e){setError(e.response?.data?.detail||e.message)}};
  return <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6"><Card className="w-full max-w-lg"><CardHeader><CardTitle className="flex gap-2"><ShieldCheck/>Secure your CA account</CardTitle></CardHeader><CardContent className="space-y-4"><p className="text-sm text-slate-600">Privileged firm accounts require an authenticator code before accessing taxpayer data.</p>{setup&&<><div className="rounded bg-slate-100 p-3 break-all text-sm"><b>Authenticator secret:</b> {setup.secret}</div><div className="text-xs text-slate-500 break-all">{setup.otpauth_uri}</div></>}<Input placeholder="6-digit authenticator code" value={code} onChange={e=>setCode(e.target.value)} /><Button className="w-full" onClick={confirm}>Verify and continue</Button>{error&&<div className="text-sm text-red-700 bg-red-50 p-3 rounded">{String(error)}</div>}</CardContent></Card></div>;
}
