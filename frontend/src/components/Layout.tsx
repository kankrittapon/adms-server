import { useEffect, useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import type { HealthCheck } from "../api/types";
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
  const { me, loading, authError, reload } = useAuth();
  const { locale, setLocale, t } = useTranslation();

  async function logout() {
    try {
      await api.logout();
    } catch {
      // token cleared regardless
    }
    clearToken();
    // Without this, `me` from the just-ended session stays stuck in memory
    // (client-side navigate() never remounts AuthProvider) until something
    // else forces a refetch — the same class of bug as the login-side fix.
    reload();
    navigate("/login", { replace: true });
  }

  const isEnrollmentOnly = me?.role === "ENROLLMENT_OPERATOR";

  // Navigation follows the four separate jobs people actually do, so each
  // one has its own place: daily attendance, the roster, fingerprint
  // enrollment, and system administration.
  const isAdminRole = me?.role === "ADMIN";
  const NAV_GROUPS: { title: string; items: NavItem[] }[] = isEnrollmentOnly
    ? [
        {
          title: t.workflow.navFingerprintGroup,
          items: [{ to: "/enrollments", label: t.nav.enrollment }],
        },
      ]
    : [
        {
          title: t.workflow.navAttendanceGroup,
          items: [
            { to: "/", label: t.nav.dashboard },
            { to: "/daily", label: t.leave.navDaily },
            { to: "/absences", label: t.leave.navLeave },
            { to: "/monthly", label: t.leave.navMonthly },
            {
              to: "/attendance",
              label: t.nav.attendance,
              badge: "LIVE",
              badgeColor: "bg-emerald-100 text-emerald-800",
            },
          ],
        },
        {
          title: t.workflow.navPersonnelGroup,
          items: [{ to: "/personnel", label: t.nav.personnel }],
        },
        {
          title: t.workflow.navFingerprintGroup,
          items: [
            { to: "/enrollments", label: t.nav.enrollment },
            { to: "/mappings", label: t.nav.mappings },
          ],
        },
        {
          title: t.workflow.navAdminGroup,
          items: [
            { to: "/devices", label: t.nav.devices },
            { to: "/system", label: t.nav.system },
            ...(isAdminRole
              ? [
                  { to: "/terminal-management", label: t.terminalManagement.title },
                  { to: "/audit", label: t.nav.audit },
                ]
              : []),
          ],
        },
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
          {NAV_GROUPS.map((g) => (
            <div key={g.title}>
              <div className="px-2.5 pb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-400">
                {g.title}
              </div>
              <div className="space-y-0.5">
                {g.items.map((n) => (
                  <NavLinkItem key={n.to} item={n} />
                ))}
              </div>
            </div>
          ))}
        </nav>

        {/* User Footer with Role Pill */}
        <div className="border-t border-slate-200 p-3 bg-slate-50/50">
          <div className="flex items-center justify-between px-2 py-1.5">
            <div className="min-w-0 pr-2">
              <div className="truncate text-xs font-bold text-slate-900">
                {loading ? t.roles.loadingAccount : me?.display_name || "Operator"}
              </div>
              <div className="flex items-center gap-1.5 mt-0.5">
                {/* Identity is unknown (still loading, or auth/me failed) ≠ VIEWER.
                    Never collapse "unknown" into the lowest-privilege role label —
                    show an explicit loading/error state until the real role is
                    proven by the backend. */}
                <span className="inline-flex items-center rounded px-1.5 py-0.2 text-[10px] font-semibold bg-slate-200 text-slate-700">
                  {loading
                    ? t.roles.loadingAccount
                    : authError
                    ? t.roles.sessionErrorTitle
                    : me?.role === "ADMIN"
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
              <span className="text-xs font-semibold text-slate-700">{t.common.productionEnvironmentLabel} 192.168.1.248</span>
            </div>
            <span className="text-slate-300">|</span>
            <DeviceStatus />
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
          {authError && (
            <div className="mb-4 flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 px-4 py-3">
              <div>
                <div className="text-sm font-bold text-rose-800">{t.roles.sessionErrorTitle}</div>
                <div className="text-xs text-rose-700 mt-0.5">{t.roles.sessionErrorBody}</div>
              </div>
              <button
                onClick={logout}
                className="inline-flex h-8 shrink-0 items-center justify-center rounded border border-rose-300 bg-white px-3 text-xs font-semibold text-rose-700 hover:bg-rose-100 transition-colors"
              >
                {t.roles.reloginButton}
              </button>
            </div>
          )}
          <WriteWindowBanner />
          <Outlet />
        </main>
      </div>
    </div>
  );
}

// The collector rewrites its health file every few seconds; older than
// this means the listener itself is down, so the state is unknown.
const HEALTH_STALE_MS = 2 * 60 * 1000;

/** Real scanner connectivity from the collector health file, polled — not a
 * hard-coded "LIVE". */
function DeviceStatus() {
  const { t, locale } = useTranslation();
  const [health, setHealth] = useState<HealthCheck | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .health()
        .then((h) => alive && setHealth(h))
        .catch(() => alive && setHealth(null));
    load();
    const id = setInterval(load, 30_000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const c = health?.collector;
  const fresh = c?.updated_at ? Date.now() - new Date(c.updated_at).getTime() < HEALTH_STALE_MS : false;
  const state = !c || !fresh ? "unknown" : c.device_connected ? "live" : "offline";
  const lastSeen = c?.last_connect_success
    ? new Date(c.last_connect_success.endsWith("Z") || c.last_connect_success.includes("+") ? c.last_connect_success : `${c.last_connect_success}Z`).toLocaleString(
        locale === "th" ? "th-TH" : "en-GB",
        { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }
      )
    : null;

  return (
    <div className="flex items-center gap-1.5 text-xs text-slate-600" title={lastSeen ? `${t.leave.deviceLastSeen}: ${lastSeen}` : undefined}>
      <span className="font-mono text-slate-500">192.168.1.201</span>
      {state === "live" ? (
        <span className="font-semibold text-emerald-600">● {t.leave.deviceLive}</span>
      ) : state === "offline" ? (
        <span className="font-semibold text-slate-500">
          ○ {t.leave.deviceOffline}
          {lastSeen && <span className="ml-1 font-normal">({t.leave.deviceLastSeen} {lastSeen})</span>}
        </span>
      ) : (
        <span className="font-semibold text-amber-600">? {t.leave.deviceUnknown}</span>
      )}
    </div>
  );
}

/** Tells write-capable users up front whether edits are possible right now,
 * instead of letting them discover it from a failed save. */
function WriteWindowBanner() {
  const { canWrite, serverWriteEnabled, writeSession, writeSessionActive, workSessionRequired } = useAuth();
  const { t, locale } = useTranslation();
  if (!canWrite || !serverWriteEnabled || !workSessionRequired) return null;
  if (writeSessionActive && writeSession?.expires_at) {
    const until = new Date(writeSession.expires_at).toLocaleTimeString(locale === "th" ? "th-TH" : "en-GB", {
      hour: "2-digit",
      minute: "2-digit",
    });
    return (
      <div className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-xs font-semibold text-emerald-800">
        ✓ {t.workflow.writeOpenBanner} {until}
      </div>
    );
  }
  return (
    <div className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5">
      <div className="text-xs font-bold text-amber-900">🔒 {t.workflow.writeClosedBanner}</div>
      <div className="mt-0.5 text-[11px] text-amber-800">{t.workflow.writeClosedHint}</div>
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
