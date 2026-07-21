import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import LoginV3 from "@/pages/v3/LoginV3";
import DashboardV3 from "@/pages/v3/DashboardV3";
import CaseWorkspaceV3 from "@/pages/v3/CaseWorkspaceV3";
import MfaSetupV3 from "@/pages/v3/MfaSetupV3";
import type { ReactNode } from "react";

const Loading = () => <div className="min-h-screen flex items-center justify-center">Loading…</div>;

function Protected({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/" replace />;
  // Only redirect to MFA if user has MFA enabled but not verified in this session
  if (user.mfa_enabled && !user.mfa_verified) return <Navigate to="/mfa" replace />;
  return <>{children}</>;
}

function RoutesV3() {
  return (
    <Routes>
      <Route path="/" element={<LoginV3 />} />
      <Route path="/mfa" element={<MfaSetupV3 />} />
      <Route path="/dashboard" element={<Protected><DashboardV3 /></Protected>} />
      <Route path="/cases/:id" element={<Protected><CaseWorkspaceV3 /></Protected>} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <RoutesV3 />
        <Toaster position="top-right" />
      </AuthProvider>
    </BrowserRouter>
  );
}
