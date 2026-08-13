import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, clearToken } from "../api/client";
import { useAuth } from "../auth";

const NAV = [
  { to: "/", label: "Dashboard" },
  { to: "/personnel", label: "Personnel" },
  { to: "/devices", label: "Devices" },
  { to: "/attendance", label: "Attendance" },
  { to: "/enrollments", label: "Enrollment" },
  { to: "/mappings", label: "Mapping" },
  { to: "/system", label: "System" },
];

export function Layout() {
  const navigate = useNavigate();
  const { me } = useAuth();

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
    <div className="flex min-h-screen bg-gray-50 text-gray-900">
      <aside className="w-56 shrink-0 border-r border-gray-200 bg-white">
        <div className="border-b border-gray-200 px-4 py-4">
          <div className="text-sm font-bold">ADMS Console</div>
          <div className="text-xs text-gray-500">Attendance Device Mgmt</div>
        </div>
        <nav className="p-2">
          {NAV.map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                `block rounded px-3 py-2 text-sm ${
                  isActive ? "bg-blue-600 text-white" : "text-gray-700 hover:bg-gray-100"
                }`
              }
            >
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-4 border-t border-gray-200 px-4 py-3">
          <div className="text-xs text-gray-500">Signed in as</div>
          <div className="truncate text-sm font-medium">{me ? me.display_name : "…"}</div>
          {me && (
            <div className="text-xs">
              <span className="rounded bg-gray-100 px-1.5 py-0.5 font-medium text-gray-600">{me.role}</span>
            </div>
          )}
          <button onClick={logout} className="mt-2 text-xs text-blue-600 hover:underline">
            Sign out
          </button>
        </div>
      </aside>
      <main className="flex-1 overflow-x-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
