import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import api from "@/lib/api";
import type { SessionResponse, SessionUser } from "@/api/types";

interface AuthValue {
  user: SessionUser | null;
  loading: boolean;
  checkAuth: () => Promise<void>;
  establishSession: (data: SessionResponse) => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    // Skip if already determined we're logged in
    if (user) return;

    setLoading(true);
    try {
      console.log("[Auth] Checking auth status...");
      const response = await api.get<SessionUser>("/auth/me", { timeout: 10000 });
      console.log("[Auth] Auth check success:", response.data);
      setUser(response.data);
    } catch (error: unknown) {
      console.log("[Auth] Auth check failed:", error);
      // Clear user on any auth failure
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, [user]);

  // Check auth on mount only
  useEffect(() => {
    void checkAuth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const establishSession = useCallback((data: SessionResponse) => {
    console.log("[Auth] Establishing session:", data);
    if (data.user) {
      setUser(data.user);
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    console.log("[Auth] Logging out...");
    try {
      await api.post("/auth/logout", {}, { timeout: 5000 });
    } catch (e) {
      console.log("[Auth] Logout API failed (ignoring):", e);
    }
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, checkAuth, establishSession, logout }),
    [user, loading, checkAuth, establishSession, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
