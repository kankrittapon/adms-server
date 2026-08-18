import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatCard } from "../components/Status";
import { WriteSessionBadge } from "../components/WriteSessionControl";
import { useTranslation } from "../i18n";

export function Dashboard() {
  const { t } = useTranslation();
  const { data, loading, error, reload } = useApi((s) => api.dashboard(s), []);

  if (loading) return <Loading />;
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <ErrorBanner message="No dashboard data" />;

  // ADMS-Dashboard-LifecycleSummary-021C: renders the SAME canonical
  // lifecycle_state buckets Enrollment Workspace/Personnel/Terminal
  // Management/Mapping use — never a raw-status grouping that could
  // disagree with them (e.g. a COMPLETED/REMOVED_FROM_TERMINAL enrollment
  // whose stored `status` column is still READY_FOR_MAPPING).
  const LIFECYCLE_ORDER = ["IN_PROGRESS", "COMPLETED", "REMOVED_FROM_TERMINAL", "CANCELLED"] as const;
  const LIFECYCLE_LABELS: Record<string, string> = {
    IN_PROGRESS: t.dashboard.lifecycleInProgress,
    COMPLETED: t.dashboard.lifecycleCompleted,
    REMOVED_FROM_TERMINAL: t.dashboard.lifecycleRemoved,
    CANCELLED: t.dashboard.lifecycleCancelled,
  };
  const lifecycleBuckets = data.enrollments_by_lifecycle_state ?? {};
  const enrollLifecycle = LIFECYCLE_ORDER.filter((k) => lifecycleBuckets[k]).map(
    (k) => [k, lifecycleBuckets[k]] as const
  );
  const isCollectorLive = data.collector?.state === "LIVE" && data.collector?.device_connected;

  return (
    <div className="space-y-6">
      {/* Top Operational Status Hero */}
      <div className="flex flex-col justify-between gap-4 rounded-xl border border-slate-200 bg-white p-5 shadow-2xs md:flex-row md:items-center">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="flex h-3 w-3 rounded-full bg-emerald-500 animate-pulse" />
            <h1 className="text-lg font-bold tracking-tight text-slate-900">{t.dashboard.title}</h1>
          </div>
          <p className="mt-1 text-xs text-slate-500">
            {t.system.collectorService}: <strong>{data.collector?.state === "LIVE" ? t.status.collectorLive : (data.collector?.state ?? "—")}</strong> · ZKTeco ZEM560:{" "}
            <strong className={isCollectorLive ? "text-emerald-700" : "text-amber-700"}>
              {data.collector?.device_connected ? "192.168.1.201 (" + t.status.deviceConnected + ")" : t.status.deviceDisconnected}
            </strong>
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <WriteSessionBadge />
          <button
            onClick={() => reload()}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50"
          >
            {t.common.refresh}
          </button>
        </div>
      </div>

      {/* KPI Stat Cards Grid */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <StatCard
          label={t.nav.personnel}
          value={data.humans_total}
          hint={`${data.humans_production_eligible} ${t.personnel.productionScope} / ${data.humans_excluded} ${t.personnel.excludedScope}`}
        />
        <StatCard
          label={t.nav.devices}
          value={data.devices_total}
          hint={`${data.devices_active} ${t.common.active} (ZEM560)`}
        />
        {/* ADMS-CurrentState-History-UXClosure-022: the primary number
            here must answer "how many accounts are on the scanner right
            now," not "how many device_users rows has the system ever
            seen." device_users_total includes historical/inactive rows
            (e.g. removed 1002/1004) — those must never inflate the
            headline KPI. device_users_active is the current count. */}
        <StatCard
          label={t.devices.currentTerminalAccounts}
          value={data.device_users_active}
          hint={`${data.device_users_total} ${t.devices.discoveredUsersHistoricalHint}`}
        />
        <StatCard
          label={t.dashboard.kpiAttendanceToday}
          value={data.attendance_today}
          hint={`${data.attendance_total} ${t.common.all} / ${data.attendance_unattributed} ${t.dashboard.kpiUnattributed}`}
        />
        {/* Same fix as the terminal-account KPI: mappings_total includes
            historical/closed mappings (e.g. Pimai's closed #2) —
            mappings_verified_active is the current-only count and must
            be the headline number. */}
        <StatCard
          label={t.mappings.verifiedMappings}
          value={data.mappings_verified_active}
          hint={`${data.mappings_total} ${t.dashboard.mappingsHistoricalHint}`}
        />
        <StatCard
          label={t.dashboard.enrollmentActiveCountLabel}
          value={data.enrollments_active_count}
          hint={t.dashboard.enrollmentActiveCountHint}
          tone={data.enrollments_active_count > 0 ? "highlight" : "normal"}
        />
        <StatCard
          label={t.system.collectorService}
          value={data.collector?.state === "LIVE" ? t.status.collectorLive : (data.collector?.state ?? "—")}
          hint={data.collector?.device_connected ? t.status.deviceConnected : t.status.deviceDisconnected}
          tone={isCollectorLive ? "highlight" : "normal"}
        />
      </div>

      {/* Enrollment Lifecycle Breakdown — operator-facing derived
          categories only, never raw DB status enums (item 5, 021C). */}
      {enrollLifecycle.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              {t.dashboard.enrollmentStatusTitle}
            </h2>
            <span className="text-xs text-slate-400">{t.dashboard.enrollmentActiveCountHint}</span>
          </div>
          <div className="flex flex-wrap gap-2.5 pt-1">
            {enrollLifecycle.map(([k, v]) => (
              <div
                key={k}
                className={`flex items-center gap-2 rounded-md border px-3 py-1.5 text-xs shadow-2xs ${
                  k === "IN_PROGRESS"
                    ? "border-blue-200 bg-blue-50"
                    : "border-slate-200 bg-slate-50"
                }`}
              >
                <span className="font-semibold text-slate-700">{LIFECYCLE_LABELS[k] ?? k}</span>
                <span className="font-mono font-bold text-slate-800">{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
