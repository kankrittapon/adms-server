import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, clearToken } from "../api/client";
import { useAuth } from "../auth";
import { WriteGateStatusBadge } from "./Status";

interface NavItem {
  to: string;
  label: string;
  badge?: string;
  badgeColor?: string;
}

const OPERATIONS_NAV: NavItem[] = [
  { to: "/", label: "Dashboard" },
  { to: "/attendance", label: "Attendance Monitor", badge: "LIVE", badgeColor: "bg-emerald-100 text-emerald-800" },
  { to: "/enrollments", label: "Enrollment Workspace", badge: "STEP", badgeColor: "bg-blue-100 text-blue-800" },
];

const IDENTITY_NAV: NavItem[] = [
  { to: "/personnel", label: "Personnel Master" },
  { to: "/mappings", label: "Identity Mapping" },
];

const INFRA_NAV: NavItem[] = [
  { to: "/devices", label: "Terminal Devices" },
  { to: "/system", label: "System Health" },
];

const ADMIN_NAV: NavItem[] = [{ to: "/audit", label: "Audit Trail" }];

export function Layout() {
  const navigate = useNavigate();
  const { me, serverWriteEnabled } = useAuth();

  async function logout() {
    try {
      await api.logout();
    } catch {
      // token cleared regardless
    }
    clearToken();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900 antialiased font-sans">
      {/* Left Sidebar Navigation */}
      <aside className="flex w-64 shrink-0 flex-col border-r border-slate-200 bg-white">
        {/* Console Header */}
        <div className="border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-600 font-mono text-sm font-bold text-white shadow-xs">
              AD
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight text-slate-900">ADMS Console</div>
              <div className="text-[11px] font-medium text-slate-500">Attendance Device Mgmt</div>
            </div>
          </div>
        </div>

        {/* Navigation Sections */}
        <nav className="flex-1 space-y-4 overflow-y-auto p-3">
          <div>
            <div className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Operations
            </div>
            <div className="space-y-0.5">
              {OPERATIONS_NAV.map((n) => (
                <NavLinkItem key={n.to} item={n} />
              ))}
            </div>
          </div>

          <div>
            <div className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Identity & People
            </div>
            <div className="space-y-0.5">
              {IDENTITY_NAV.map((n) => (
                <NavLinkItem key={n.to} item={n} />
              ))}
            </div>
          </div>

          <div>
            <div className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Infrastructure
            </div>
            <div className="space-y-0.5">
              {INFRA_NAV.map((n) => (
                <NavLinkItem key={n.to} item={n} />
              ))}
            </div>
          </div>

          {me?.role === "ADMIN" && (
            <div>
              <div className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Administration
              </div>
              <div className="space-y-0.5">
                {ADMIN_NAV.map((n) => (
                  <NavLinkItem key={n.to} item={n} />
                ))}
              </div>
            </div>
          )}
        </nav>

        {/* User Identity & Safety Status Footer */}
        <div className="border-t border-slate-200 bg-slate-50/70 p-3.5 space-y-2.5">
          {/* Write Gate Indicator Box */}
          <div className="rounded-md border border-slate-200 bg-white p-2.5 shadow-2xs">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Server Write Gate</div>
            <div className="mt-1">
              <WriteGateStatusBadge writeEnabled={serverWriteEnabled} />
            </div>
            <div className="mt-1 text-[11px] text-slate-500">
              {serverWriteEnabled
                ? "Mutations & device writes unlocked."
                : "Safe mode: writes blocked on server."}
            </div>
          </div>

          {/* User profile */}
          <div className="flex items-center justify-between pt-1">
            <div className="min-w-0 pr-2">
              <div className="truncate text-xs font-bold text-slate-900">{me?.display_name ?? "..."}</div>
              <div className="mt-0.5 flex items-center gap-1.5">
                <span className="inline-block rounded bg-slate-200 px-1.5 py-0.2 text-[10px] font-bold text-slate-700">
                  {me?.role ?? "VIEWER"}
                </span>
                <span className="text-[10px] text-slate-400">({me?.username})</span>
              </div>
            </div>
            <button
              onClick={logout}
              className="rounded border border-slate-200 bg-white px-2 py-1 text-[11px] font-semibold text-slate-600 hover:bg-slate-100 hover:text-slate-900 shadow-2xs transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      {/* Main Layout Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Persistent Operational Bar */}
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-slate-500">Host:</span>
            <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs font-semibold text-slate-700 border border-slate-200">
              Production (192.168.1.248)
            </span>
          </div>

          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500 font-medium">Terminal ZEM560:</span>
              <span className="inline-flex items-center gap-1 font-semibold text-emerald-700">
                <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                192.168.1.201
              </span>
            </div>

            <div className="h-4 w-px bg-slate-200" />

            <div className="flex items-center gap-1.5">
              <span className="text-slate-500 font-medium">Write Mode:</span>
              <WriteGateStatusBadge writeEnabled={serverWriteEnabled} />
            </div>
          </div>
        </header>

        {/* Page Content Container */}
        <main className="flex-1 overflow-auto p-6">
          <div className="mx-auto max-w-7xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

function NavLinkItem({ item }: { item: NavItem }) {
  return (
    <NavLink
      to={item.to}
      end={item.to === "/"}
      className={({ isActive }) =>
        `flex items-center justify-between rounded-md px-3 py-2 text-xs font-medium transition-colors ${
          isActive
            ? "bg-blue-600 text-white font-semibold shadow-xs"
            : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
        }`
      }
    >
      <span>{item.label}</span>
      {item.badge && (
        <span
          className={`rounded px-1.5 py-0.2 text-[9px] font-bold uppercase tracking-wider ${
            item.badgeColor ?? "bg-slate-200 text-slate-700"
          }`}
        >
          {item.badge}
        </span>
      )}
    </NavLink>
  );
}
