import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { ShieldCheck, Calculator, AlertCircle } from "lucide-react";
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
  const [validationErrors, setValidationErrors] = useState({});
  if (user) return <Navigate to="/dashboard" replace />;

  // Client-side validation
  const validateForm = () => {
    const errors = {};

    if (mode === "bootstrap") {
      if (!form.firm_name || form.firm_name.length < 2) {
        errors.firm_name = "Firm name must be at least 2 characters";
      }
      if (!form.firm_slug || form.firm_slug.length < 3) {
        errors.firm_slug = "Firm slug must be at least 3 characters";
      } else if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(form.firm_slug)) {
        errors.firm_slug = "Use lowercase letters, numbers, and hyphens only (no leading/trailing hyphens)";
      }
      if (!form.owner_name || form.owner_name.length < 2) {
        errors.owner_name = "Name must be at least 2 characters";
      }
      if (!form.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
        errors.email = "Please enter a valid email address";
      }
      if (!form.password || form.password.length < 12) {
        errors.password = "Password must be at least 12 characters";
      }
    } else if (mode === "login") {
      if (!form.email || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) {
        errors.email = "Please enter a valid email address";
      }
      if (!form.password) {
        errors.password = "Password is required";
      }
    }

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const update = (key) => (e) => {
    setForm((current) => ({ ...current, [key]: e.target.value }));
    // Clear validation error for this field when user types
    if (validationErrors[key]) {
      setValidationErrors((current) => ({ ...current, [key]: undefined }));
    }
  };

  const submit = async (event) => {
    event.preventDefault();
    setError("");

    // Run client-side validation first
    if (!validateForm()) {
      return;
    }

    setBusy(true);
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
      // Handle server-side validation errors
      if (err.response?.data?.errors && Array.isArray(err.response.data.errors)) {
        const serverErrors = {};
        err.response.data.errors.forEach((e) => {
          const field = e.loc?.[1] || 'unknown';
          serverErrors[field] = e.msg || e.type;
        });
        setValidationErrors(serverErrors);
        setError("Please fix the errors below");
      } else {
        setError(err.response?.data?.detail || err.message || "Unable to sign in. Please try again.");
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 grid lg:grid-cols-2">
      <div className="hidden lg:flex p-16 bg-slate-950 text-white flex-col justify-between">
        <div className="flex gap-3 items-center">
          <Calculator className="h-8 w-8" />
          <span className="font-display text-2xl">Green Papaya</span>
        </div>
        <div>
          <h1 className="text-5xl font-semibold leading-tight">Evidence-linked tax preparation for CA firms.</h1>
          <p className="mt-6 text-slate-300 text-lg">Deterministic computation, maker-checker review, secure documents and controlled AI assistance.</p>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-300">
          <ShieldCheck className="h-5 w-5" />
          Every material number remains reviewable and reproducible.
        </div>
      </div>

      <div className="flex items-center justify-center p-6">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>
              {mode === "bootstrap" ? "Create your CA firm" : mode === "invitation" ? "Accept firm invitation" : "Sign in to your firm"}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={submit}>
              {mode === "bootstrap" && (
                <>
                  <div>
                    <Input
                      placeholder="Firm name (e.g., Sharma & Associates)"
                      value={form.firm_name}
                      onChange={update("firm_name")}
                    />
                    {validationErrors.firm_name && <p className="text-xs text-red-500 mt-1">{validationErrors.firm_name}</p>}
                  </div>
                  <div>
                    <Input
                      placeholder="Firm slug (e.g., sharma-ca) - lowercase only"
                      value={form.firm_slug}
                      onChange={update("firm_slug")}
                    />
                    {validationErrors.firm_slug && <p className="text-xs text-red-500 mt-1">{validationErrors.firm_slug}</p>}
                  </div>
                  <div>
                    <Input
                      placeholder="Your full name"
                      value={form.owner_name}
                      onChange={update("owner_name")}
                    />
                    {validationErrors.owner_name && <p className="text-xs text-red-500 mt-1">{validationErrors.owner_name}</p>}
                  </div>
                </>
              )}

              {mode === "invitation" && (
                <Input
                  placeholder="Your full name"
                  value={form.owner_name}
                  onChange={update("owner_name")}
                  required
                />
              )}

              {mode !== "invitation" && (
                <div>
                  <Input
                    type="email"
                    placeholder="Email address"
                    value={form.email}
                    onChange={update("email")}
                  />
                  {validationErrors.email && <p className="text-xs text-red-500 mt-1">{validationErrors.email}</p>}
                </div>
              )}

              <div>
                <Input
                  type="password"
                  placeholder={mode === "bootstrap" ? "Password (min 12 characters)" : "Password"}
                  value={form.password}
                  onChange={update("password")}
                />
                {validationErrors.password && <p className="text-xs text-red-500 mt-1">{validationErrors.password}</p>}
              </div>

              {mode === "login" && (
                <>
                  <Input
                    placeholder="Firm slug (only if you belong to multiple firms)"
                    value={form.tenant_slug}
                    onChange={update("tenant_slug")}
                  />
                  <Input
                    placeholder="6-digit MFA code (if enabled)"
                    value={form.totp_code}
                    onChange={update("totp_code")}
                  />
                </>
              )}

              {error && (
                <div className="flex items-start gap-2 rounded-md bg-red-50 p-3 text-sm text-red-700">
                  <AlertCircle className="h-4 w-4 mt-0.5 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? "Please wait…" : mode === "bootstrap" ? "Create firm" : mode === "invitation" ? "Accept invitation" : "Sign in"}
              </Button>
            </form>

            {!invitationToken && (
              <button
                className="mt-4 text-sm text-center w-full text-slate-600 hover:text-slate-900 underline"
                onClick={() => {
                  setMode(mode === "login" ? "bootstrap" : "login");
                  setError("");
                  setValidationErrors({});
                }}
              >
                {mode === "login" ? "First time? Create your CA firm" : "Already have an account? Sign in"}
              </button>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
