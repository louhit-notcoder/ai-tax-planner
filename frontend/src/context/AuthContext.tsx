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
  const [initialized, setInitialized] = useState(false);

  const checkAuth = useCallback(async () => {
    // Prevent multiple simultaneous checks
    if (!loading && initialized && user) return;

    try {
      console.log("[Auth] Checking auth status...");
      const response = await api.get<SessionUser>("/auth/me", {
        timeout: 15000,
        headers: { 'X-Request-ID': `auth-check-${Date.now()}` }
      });
      console.log("[Auth] Auth check success:", response.data);
      setUser(response.data);
      setLoading(false);
      setInitialized(true);
    } catch (error: unknown) {
      console.log("[Auth] Auth check failed:", error);
      // 401 = not logged in (OK)
      // Network error = might be temporary
      if (error && typeof error === 'object') {
        const axiosError = error as { response?: { status?: number }; message?: string };
        if (axiosError.response?.status === 401) {
          console.log("[Auth] Not authenticated (401)");
          setUser(null);
        } else if (axiosError.message === "Network Error") {
          console.log("[Auth] Network error - keeping current state");
          // Don't change user state on network error
          // This prevents the logout loop
        }
      }
      setLoading(false);
      setInitialized(true);
    }
  }, [loading, initialized, user]);

  // Check auth once on mount
  useEffect(() => {
    console.log("[Auth] AuthProvider mounted");
    void checkAuth();
  }, []);

  const establishSession = useCallback((data: SessionResponse) => {
    console.log("[Auth] Establishing session:", data.user);
    if (data.user) {
      setUser(data.user);
      setLoading(false);
      setInitialized(true);
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
    setLoading(false);
  }, []);

  const value = useMemo(
    () => ({ user, loading, checkAuth, establishSession, logout }),
    [user, loading, checkAuth, establishSession, logout]
  );

  console.log("[Auth] Provider render - loading:", loading, "user:", !!user);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthProvider");
  }
  return value;
}
