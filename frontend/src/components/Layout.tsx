import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, clearToken } from "../api/client";
import { useAuth } from "../auth";

const NAV = [
  { to: "/", label: "Dashboard" },
  { to: "/personnel", label: "Personnel" },
  { to: "/devices", label: "Devices" },
  { to: "/attendance", label: "Attendance" },
  { to: "/enrollments", label: "Enrollment Workspace" },
  { to: "/mappings", label: "Mapping" },
  { to: "/system", label: "System" },
];

const ADMIN_NAV = [{ to: "/audit", label: "Audit Trail" }];

export function Layout() {
  const navigate = useNavigate();
  const { me, serverWriteEnabled } = useAuth();

  async function logout() {
    try {
      await api.logout();
    } catch {
      // ignore — token is cleared regardless
    }
    clearToken();
    navigate("/login", { replace: true });
  }

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900 antialiased">
      {/* Sidebar */}
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="border-b border-slate-200 px-5 py-4">
          <div className="flex items-center gap-2">
            <div className="flex h-7 w-7 items-center justify-center rounded bg-blue-600 font-mono text-sm font-bold text-white shadow-sm">
              AD
            </div>
            <div>
              <div className="text-sm font-bold tracking-tight text-slate-900">ADMS Console</div>
              <div className="text-[11px] font-medium text-slate-500">Device Management</div>
            </div>
          </div>
        </div>

        {/* Navigation items */}
        <nav className="flex-1 space-y-0.5 p-3">
          <div className="px-2 pb-1.5 pt-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
            Operations
          </div>
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                `flex items-center justify-between rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                  isActive
                    ? "bg-blue-600 text-white shadow-sm"
                    : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
                }`
              }
            >
              <span>{n.label}</span>
              {n.to === "/enrollments" && (
                <span
                  className="rounded px-1.5 py-0.2 text-[9px] font-semibold uppercase tracking-wide bg-blue-100 text-blue-700 data-[active=true]:bg-blue-500 data-[active=true]:text-white"
                >
                  Step
                </span>
              )}
            </NavLink>
          ))}

          {me?.role === "ADMIN" && (
            <>
              <div className="mt-4 px-2 pb-1.5 pt-1 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Administration
              </div>
              {ADMIN_NAV.map((n) => (
                <NavLink
                  key={n.to}
                  to={n.to}
                  className={({ isActive }) =>
                    `flex items-center justify-between rounded-md px-3 py-2 text-xs font-medium transition-colors ${
                      isActive
                        ? "bg-blue-600 text-white shadow-sm"
                        : "text-slate-700 hover:bg-slate-100 hover:text-slate-900"
                    }`
                  }
                >
                  <span>{n.label}</span>
                </NavLink>
              ))}
            </>
          )}
        </nav>

        {/* User profile & Write status box */}
        <div className="border-t border-slate-200 bg-slate-50/70 p-3.5">
          <div className="mb-2 rounded border border-slate-200 bg-white p-2.5 shadow-2xs">
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold">Write Gate</span>
              {serverWriteEnabled ? (
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-emerald-700">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                  LIVE
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-700" title="API_WRITE_ENABLED=false">
                  <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                  LOCKED
                </span>
              )}
            </div>
            <div className="mt-1 text-[11px] text-slate-600">
              {serverWriteEnabled
                ? "Mutations enabled"
                : "Read-only mode"}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div className="min-w-0 pr-2">
              <div className="truncate text-xs font-semibold text-slate-900">{me?.display_name ?? "..."}</div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="inline-block rounded bg-slate-200 px-1.5 py-0.2 text-[10px] font-semibold text-slate-700">
                  {me?.role ?? "..."}
                </span>
              </div>
            </div>
            <button
              onClick={logout}
              className="rounded border border-slate-200 bg-white px-2 py-1 text-[11px] font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900 shadow-2xs transition-colors"
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top Operational Status Bar */}
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
          <div className="flex items-center gap-3">
            <span className="text-xs font-semibold text-slate-500">System Environment:</span>
            <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs font-medium text-slate-700">
              Production (192.168.1.248)
            </span>
          </div>

          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <span className="text-slate-500 font-medium">Terminal ZEM560:</span>
              <span className="inline-flex items-center gap-1 font-semibold text-emerald-700">
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                192.168.1.201
              </span>
            </div>

            <div className="h-4 w-px bg-slate-200" />

            <div className="flex items-center gap-1.5">
              <span className="text-slate-500 font-medium">Write Status:</span>
              {serverWriteEnabled ? (
                <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 border border-emerald-200">
                  Production Writes Active
                </span>
              ) : (
                <span className="rounded-full bg-amber-50 px-2 py-0.5 font-medium text-amber-800 border border-amber-200">
                  Writes Locked (API_WRITE_ENABLED=false)
                </span>
              )}
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
