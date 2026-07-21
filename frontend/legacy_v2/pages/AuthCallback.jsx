import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;

    const hash = window.location.hash;
    const match = hash.match(/session_id=([^&]+)/);
    const sessionId = match ? match[1] : null;

    const run = async () => {
      if (!sessionId) { navigate("/"); return; }
      try {
        const res = await api.post("/auth/session", { session_id: sessionId });
        if (res.data.session_token) localStorage.setItem("gp_token", res.data.session_token);
        const u = res.data.user;
        setUser(u);
        window.history.replaceState(null, "", window.location.pathname);
        if (!u.role || u.role === "unset") navigate("/select-role", { state: { user: u } });
        else navigate(u.role === "ca_partner" ? "/ca" : "/dashboard", { state: { user: u } });
      } catch (e) {
        navigate("/");
      }
    };
    run();
  }, [navigate, setUser]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-background">
      <div className="text-center rise">
        <div className="font-display display-xl text-graphite">Signing you in</div>
        <p className="text-steel mt-3">Securely establishing your encrypted session…</p>
      </div>
    </div>
  );
}
