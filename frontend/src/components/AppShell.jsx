import { Link, useLocation } from "react-router-dom";
import { Logo } from "@/components/Logo";
import { useAuth } from "@/context/AuthContext";
import { LogOut } from "lucide-react";

export default function AppShell({ children, links = [] }) {
  const { user, logout } = useAuth();
  const loc = useLocation();
  return (
    <div className="min-h-screen bg-fog">
      <header className="bg-background border-b border-mist sticky top-0 z-40">
        <div className="max-w-[1280px] mx-auto px-6 h-[68px] flex items-center justify-between">
          <div className="flex items-center gap-8">
            <Logo to={user?.role === "ca_partner" ? "/ca" : "/dashboard"} />
            <nav className="hidden md:flex items-center gap-1">
              {links.map((l) => {
                const active = loc.pathname === l.to;
                return (
                  <Link key={l.to} to={l.to} data-testid={`nav-${l.label.toLowerCase().replace(/\s/g, "-")}`}
                    className={`font-display text-[15px] px-4 py-2 rounded-none transition-colors ${active ? "text-ember" : "text-graphite hover:text-ember"}`}>
                    {l.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden sm:flex items-center gap-2.5">
              {user?.picture
                ? <img src={user.picture} alt="" className="h-8 w-8 rounded-full object-cover" referrerPolicy="no-referrer" />
                : <div className="h-8 w-8 rounded-full bg-ash flex items-center justify-center font-display text-sm">{user?.name?.[0]}</div>}
              <div className="leading-tight">
                <div className="text-[13px] font-display text-graphite">{user?.name}</div>
                <div className="text-[11px] text-slate-ink capitalize">{user?.role === "ca_partner" ? "Chartered Accountant" : "Taxpayer"}</div>
              </div>
            </div>
            <button onClick={logout} data-testid="logout-btn"
              className="flex items-center gap-2 text-slate-ink hover:text-graphite transition-colors text-sm">
              <LogOut className="h-4 w-4" /> <span className="hidden sm:inline">Logout</span>
            </button>
          </div>
        </div>
      </header>
      <main className="max-w-[1280px] mx-auto px-6 py-10">{children}</main>
    </div>
  );
}
