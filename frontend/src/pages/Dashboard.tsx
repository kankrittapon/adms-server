import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatCard, StatusBadge, WriteGateStatusBadge } from "../components/Status";
import { useAuth } from "../auth";
import { useTranslation } from "../i18n";

export function Dashboard() {
  const { serverWriteEnabled } = useAuth();
  const { t } = useTranslation();
  const { data, loading, error, reload } = useApi((s) => api.dashboard(s), []);

  if (loading) return <Loading />;
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <ErrorBanner message="No dashboard data" />;

  const enrollStatus = Object.entries(data.enrollments_by_status ?? {});
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
          <WriteGateStatusBadge writeEnabled={serverWriteEnabled} />
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
        <StatCard
          label={t.devices.discoveredUsers}
          value={data.device_users_total}
          hint={`${data.device_users_active} ${t.common.active}`}
        />
        <StatCard
          label={t.dashboard.kpiAttendanceToday}
          value={data.attendance_today}
          hint={`${data.attendance_total} ${t.common.all} / ${data.attendance_unattributed} ${t.dashboard.kpiUnattributed}`}
        />
        <StatCard
          label={t.mappings.verifiedMappings}
          value={data.mappings_total}
          hint={`${data.mappings_verified_active} ${t.mappings.activeMapping}`}
        />
        <StatCard
          label={t.system.collectorService}
          value={data.collector?.state === "LIVE" ? t.status.collectorLive : (data.collector?.state ?? "—")}
          hint={data.collector?.device_connected ? t.status.deviceConnected : t.status.deviceDisconnected}
          tone={isCollectorLive ? "highlight" : "normal"}
        />
      </div>

      {/* Active Enrollments Breakdown */}
      {enrollStatus.length > 0 && (
        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 pb-2.5">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              {t.dashboard.enrollmentStatusTitle}
            </h2>
            <span className="text-xs text-slate-400">Live workflow breakdown</span>
          </div>
          <div className="flex flex-wrap gap-2.5 pt-1">
            {enrollStatus.map(([k, v]) => (
              <div
                key={k}
                className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs shadow-2xs"
              >
                <StatusBadge status={k} />
                <span className="font-mono font-bold text-slate-800">{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
