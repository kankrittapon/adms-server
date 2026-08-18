import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, clearToken } from "../api/client";
import { useAuth } from "../auth";
import { useTranslation } from "../i18n";
import { WriteSessionBadge } from "./WriteSessionControl";

interface NavItem {
  to: string;
  label: string;
  badge?: string;
  badgeColor?: string;
}

export function Layout() {
  const navigate = useNavigate();
  const { me } = useAuth();
  const { locale, setLocale, t } = useTranslation();

  async function logout() {
    try {
      await api.logout();
    } catch {
      // token cleared regardless
    }
    clearToken();
    navigate("/login", { replace: true });
  }

  const isEnrollmentOnly = me?.role === "ENROLLMENT_OPERATOR";

  const OPERATIONS_NAV: NavItem[] = isEnrollmentOnly
    ? [
        {
          to: "/enrollments",
          label: t.nav.enrollment,
          badge: "STEP",
          badgeColor: "bg-blue-100 text-blue-800",
        },
      ]
    : [
        { to: "/", label: t.nav.dashboard },
        {
          to: "/attendance",
          label: t.nav.attendance,
          badge: "LIVE",
          badgeColor: "bg-emerald-100 text-emerald-800",
        },
        {
          to: "/enrollments",
          label: t.nav.enrollment,
          badge: "STEP",
          badgeColor: "bg-blue-100 text-blue-800",
        },
      ];

  const IDENTITY_NAV: NavItem[] = [
    { to: "/personnel", label: t.nav.personnel },
    { to: "/mappings", label: t.nav.mappings },
  ];

  const INFRA_NAV: NavItem[] = [
    { to: "/devices", label: t.nav.devices },
    { to: "/system", label: t.nav.system },
  ];

  const ADMIN_NAV: NavItem[] = [
    { to: "/terminal-management", label: t.terminalManagement.title },
    { to: "/audit", label: t.nav.audit },
  ];

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
              <div className="text-sm font-bold tracking-tight text-slate-900">{t.common.systemSubtitle}</div>
              <div className="text-[11px] font-medium text-slate-500">{t.common.systemTitle}</div>
            </div>
          </div>
        </div>

        {/* Navigation Sections */}
        <nav className="flex-1 space-y-4 overflow-y-auto p-3">
          <div>
            <div className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
              {t.nav.operations}
            </div>
            <div className="space-y-0.5">
              {OPERATIONS_NAV.map((n) => (
                <NavLinkItem key={n.to} item={n} />
              ))}
            </div>
          </div>

          {!isEnrollmentOnly && (
            <>
              <div>
                <div className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  {t.nav.identityPeople}
                </div>
                <div className="space-y-0.5">
                  {IDENTITY_NAV.map((n) => (
                    <NavLinkItem key={n.to} item={n} />
                  ))}
                </div>
              </div>

              <div>
                <div className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  {t.nav.infrastructure}
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
                    {t.nav.administration}
                  </div>
                  <div className="space-y-0.5">
                    {ADMIN_NAV.map((n) => (
                      <NavLinkItem key={n.to} item={n} />
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </nav>

        {/* User Footer with Role Pill */}
        <div className="border-t border-slate-200 p-3 bg-slate-50/50">
          <div className="flex items-center justify-between px-2 py-1.5">
            <div className="min-w-0 pr-2">
              <div className="truncate text-xs font-bold text-slate-900">{me?.display_name || "Operator"}</div>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="inline-flex items-center rounded px-1.5 py-0.2 text-[10px] font-semibold bg-slate-200 text-slate-700">
                  {me?.role === "ADMIN"
                    ? t.roles.admin
                    : me?.role === "ENROLLMENT_OPERATOR"
                    ? t.roles.enrollmentOperator
                    : me?.role === "OPERATOR"
                    ? t.roles.operator
                    : t.roles.viewer}
                </span>
              </div>
            </div>
            <button
              onClick={logout}
              title={t.nav.signOut}
              className="inline-flex h-7 items-center justify-center rounded border border-slate-300 bg-white px-2 text-[11px] font-semibold text-slate-700 hover:bg-slate-100 hover:text-slate-900 transition-colors shadow-2xs"
            >
              {t.nav.signOut}
            </button>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Global Operational Header Bar */}
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white px-6">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              <span className="text-xs font-semibold text-slate-700">Production 192.168.1.248</span>
            </div>
            <span className="text-slate-300">|</span>
            <div className="flex items-center gap-1.5 text-xs text-slate-600">
              <span className="font-mono text-slate-500">192.168.1.201</span>
              <span className="font-semibold text-emerald-600">● LIVE</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* TH / EN Language Switcher */}
            <div className="inline-flex rounded-lg border border-slate-200 bg-slate-100 p-0.5 shadow-2xs">
              <button
                type="button"
                onClick={() => setLocale("th")}
                className={`rounded-md px-2.5 py-1 text-xs font-bold transition-all ${
                  locale === "th"
                    ? "bg-white text-blue-700 shadow-xs ring-1 ring-slate-200"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                TH
              </button>
              <button
                type="button"
                onClick={() => setLocale("en")}
                className={`rounded-md px-2.5 py-1 text-xs font-bold transition-all ${
                  locale === "en"
                    ? "bg-white text-blue-700 shadow-xs ring-1 ring-slate-200"
                    : "text-slate-600 hover:text-slate-900"
                }`}
              >
                EN
              </button>
            </div>

            <WriteSessionBadge />
          </div>
        </header>

        {/* Dynamic Page View Container */}
        <main className="flex-1 overflow-y-auto p-6 bg-slate-50">
          <Outlet />
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
        `flex items-center justify-between rounded-md px-2.5 py-2 text-xs font-medium transition-colors ${
          isActive
            ? "bg-blue-50 text-blue-700 font-semibold shadow-2xs"
            : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
        }`
      }
    >
      <span>{item.label}</span>
      {item.badge && (
        <span className={`rounded px-1.5 py-0.2 text-[10px] font-bold ${item.badgeColor ?? "bg-slate-200 text-slate-700"}`}>
          {item.badge}
        </span>
      )}
    </NavLink>
  );
}
