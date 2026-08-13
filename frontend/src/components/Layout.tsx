import { NavLink, Outlet } from "react-router-dom";

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
      </aside>
      <main className="flex-1 overflow-x-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}
