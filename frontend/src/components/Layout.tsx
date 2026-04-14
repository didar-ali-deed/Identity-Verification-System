import { Link, Outlet, useNavigate, useLocation } from "react-router-dom";
import { useAuthStore } from "@/stores/authStore";
import { Shield, LogOut, User, FileCheck, LayoutDashboard } from "lucide-react";

export default function Layout() {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    await logout();
    navigate("/login");
  };

  const isActive = (path: string) =>
    location.pathname === path || location.pathname.startsWith(path + "/");

  return (
    <div className="min-h-screen bg-background">
      {/* ── Top navbar ── */}
      <header className="sticky top-0 z-50 border-b border-border bg-[#040d1a]/90 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-14">

            {/* Logo */}
            <Link to="/" className="flex items-center gap-2.5 no-underline group">
              <Shield className="h-6 w-6 text-primary logo-glow" />
              <span
                className="text-base font-bold tracking-tight"
                style={{ fontFamily: "Syne, sans-serif" }}
              >
                <span className="text-primary">IDV</span>
                <span className="text-foreground"> Verify</span>
              </span>
            </Link>

            {/* Nav links */}
            <nav className="flex items-center gap-1">
              {user?.role === "admin" && (
                <Link
                  to="/admin"
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all no-underline ${
                    isActive("/admin")
                      ? "bg-primary/15 text-primary"
                      : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                  }`}
                >
                  <LayoutDashboard className="h-4 w-4" />
                  <span className="hidden sm:inline">Dashboard</span>
                </Link>
              )}

              <Link
                to="/idv"
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-all no-underline ${
                  isActive("/idv")
                    ? "bg-primary/15 text-primary"
                    : "text-muted-foreground hover:text-foreground hover:bg-white/5"
                }`}
              >
                <FileCheck className="h-4 w-4" />
                <span className="hidden sm:inline">Verification</span>
              </Link>

              {/* User + logout */}
              <div className="flex items-center gap-2 pl-3 ml-1 border-l border-border">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-primary/20 border border-primary/30 flex items-center justify-center shrink-0">
                    <User className="h-3.5 w-3.5 text-primary" />
                  </div>
                  <span className="text-sm font-medium text-foreground hidden md:block">
                    {user?.full_name?.split(" ")[0]}
                  </span>
                </div>
                <button
                  onClick={handleLogout}
                  title="Sign out"
                  className="p-1.5 rounded-md text-muted-foreground hover:text-destructive hover:bg-red-500/10 transition-all cursor-pointer bg-transparent border-none"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </nav>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Outlet />
      </main>
    </div>
  );
}
