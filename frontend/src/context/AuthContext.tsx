import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import api from "@/lib/api";
import type { SessionResponse, SessionUser } from "@/api/types";

interface AuthValue { user: SessionUser | null; loading: boolean; checkAuth: () => Promise<void>; establishSession: (data: SessionResponse) => void; logout: () => Promise<void>; }
const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: {children: ReactNode}) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);
  const checkAuth = useCallback(async () => {
    try { const {data}=await api.get<SessionUser>("/auth/me"); setUser(data); }
    catch { setUser(null); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void checkAuth(); }, [checkAuth]);
  const establishSession = useCallback((data: SessionResponse) => { setUser(data.user); }, []);
  const logout = useCallback(async()=>{try{await api.post("/auth/logout",{});}catch{/* clear local state regardless */}setUser(null);},[]);
  const value=useMemo(()=>({user,loading,checkAuth,establishSession,logout}),[user,loading,checkAuth,establishSession,logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
export function useAuth(){const value=useContext(AuthContext);if(!value)throw new Error("useAuth must be used inside AuthProvider");return value;}
