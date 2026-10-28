import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { todayLocal } from "./Absences";
import { TrialBanner } from "./DailyRoster";
import { ErrorBanner, Loading, StatCard } from "../components/Status";
import { WriteSessionBadge } from "../components/WriteSessionControl";
import { useTranslation } from "../i18n";

/** Technical system counters (kept below the attendance overview). */
function SystemOverview() {
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
    <details className="space-y-6 rounded-xl border border-slate-200 bg-white p-4 shadow-2xs">
      <summary className="cursor-pointer text-xs font-bold uppercase tracking-wider text-slate-500">ข้อมูลระบบ (เทคนิค)</summary>
      <div className="mt-4 space-y-6">
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
    </details>
  );
}

const TILES = [
  { key: "PRESENT", cls: "border-emerald-200 bg-emerald-50 text-emerald-800", bar: "bg-emerald-500" },
  { key: "LATE", cls: "border-orange-200 bg-orange-50 text-orange-800", bar: "bg-orange-400" },
  { key: "LEAVE", cls: "border-amber-200 bg-amber-50 text-amber-800", bar: "bg-amber-400" },
  { key: "DUTY", cls: "border-sky-200 bg-sky-50 text-sky-800", bar: "bg-sky-500" },
  { key: "ABSENT", cls: "border-rose-200 bg-rose-50 text-rose-800", bar: "bg-rose-500" },
  { key: "NOT_YET", cls: "border-slate-200 bg-slate-50 text-slate-700", bar: "bg-slate-300" },
] as const;

/** Last n weekdays (Mon–Fri) ending today, oldest first. */
function recentWeekdays(n: number): string[] {
  const out: string[] = [];
  const d = new Date(`${todayLocal()}T00:00:00`);
  while (out.length < n) {
    const dow = d.getDay();
    if (dow !== 0 && dow !== 6) {
      out.unshift(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`);
    }
    d.setDate(d.getDate() - 1);
  }
  return out;
}

const cnt = (totals: unknown, k: string) => Number((totals as Record<string, number> | undefined)?.[k] ?? 0);

export function Dashboard() {
  const { t } = useTranslation();
  const today = todayLocal();
  const roster = useApi((s) => api.dailyRoster(today, s), [today]);
  const readiness = useApi((s) => api.readiness(s), []);
  const health = useApi((s) => api.dashboard(s), []);
  const days = recentWeekdays(7);
  const week = useApi((s) => Promise.all(days.map((d) => api.dailyRoster(d, s))), [today]);
  const label = (k: string) => t.leave[`st_${k}` as "st_PRESENT"];

  const r = roster.data;
  const deviceOk = health.data?.collector?.state === "LIVE" && health.data?.collector?.device_connected;
  const rd = readiness.data?.total;
  const dateLabel = new Date(`${today}T00:00:00`).toLocaleDateString("th-TH", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 rounded-xl border border-slate-200 bg-white p-5 shadow-2xs sm:flex-row sm:items-center">
        <div>
          <h1 className="text-lg font-bold tracking-tight text-slate-900">ภาพรวมกำลังพลวันนี้</h1>
          <p className="text-xs text-slate-500">
            {dateLabel}
            {r && !r.is_workday && <> · <b>{r.holiday_name ?? "วันหยุด"}</b></>}
            {r && <> · ช่วงสแกน {r.scan_window} · สายหลัง {r.late_after}</>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`rounded-full px-3 py-1 text-xs font-bold ${deviceOk ? "bg-emerald-100 text-emerald-800" : "bg-rose-100 text-rose-800"}`}
          >
            {deviceOk ? "● เครื่องสแกนออนไลน์" : "● เครื่องสแกนออฟไลน์"}
          </span>
          <button
            type="button"
            onClick={() => {
              roster.reload();
              readiness.reload();
              health.reload();
              week.reload();
            }}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            {t.common.refresh}
          </button>
        </div>
      </div>

      <TrialBanner />

      {roster.error ? (
        <ErrorBanner message={roster.error} />
      ) : !r ? (
        <Loading />
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {TILES.map((tile) => (
            <Link key={tile.key} to="/daily" className={`rounded-lg border p-3 shadow-2xs hover:opacity-90 ${tile.cls}`}>
              <div className="text-[11px] font-semibold">{label(tile.key)}</div>
              <div className="mt-1 text-2xl font-bold">{cnt(r.totals, tile.key)}</div>
            </Link>
          ))}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs space-y-3">
          <h2 className="text-sm font-bold text-slate-900">7 วันทำการล่าสุด</h2>
          {week.error ? (
            <ErrorBanner message={week.error} />
          ) : !week.data ? (
            <Loading />
          ) : (
            <div className="space-y-1.5">
              {week.data.map((d) => {
                const parts = TILES.filter((x) => x.key !== "NOT_YET").map((x) => ({ ...x, n: cnt(d.totals, x.key) }));
                const sum = parts.reduce((a, b) => a + b.n, 0);
                return (
                  <div key={String(d.date)} className="flex items-center gap-2 text-[11px]">
                    <span className="w-16 shrink-0 text-slate-600">
                      {new Date(`${d.date}T00:00:00`).toLocaleDateString("th-TH", { weekday: "short", day: "numeric", month: "short" })}
                    </span>
                    <div className="flex h-4 flex-1 overflow-hidden rounded bg-slate-100">
                      {d.is_workday && sum > 0 ? (
                        parts.map((p) =>
                          p.n ? <div key={p.key} title={`${label(p.key)} ${p.n}`} className={p.bar} style={{ width: `${(100 * p.n) / sum}%` }} /> : null
                        )
                      ) : (
                        <span className="px-2 text-[10px] leading-4 text-slate-400">{d.is_workday ? "—" : d.holiday_name ?? "วันหยุด"}</span>
                      )}
                    </div>
                    <span className="w-14 shrink-0 text-right text-slate-600">
                      {d.is_workday && sum ? `ขาด ${cnt(d.totals, "ABSENT")}` : ""}
                    </span>
                  </div>
                );
              })}
              <div className="flex flex-wrap gap-3 pt-1 text-[10px] text-slate-500">
                {TILES.filter((x) => x.key !== "NOT_YET").map((x) => (
                  <span key={x.key} className="flex items-center gap-1">
                    <span className={`inline-block h-2 w-2 rounded-sm ${x.bar}`} /> {label(x.key)}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-bold text-slate-900">ความพร้อมการลงลายนิ้วมือ</h2>
            <Link to="/enrollments" className="text-[11px] font-semibold text-blue-600 hover:underline">ไปหน้าลงนิ้ว →</Link>
          </div>
          {readiness.error ? (
            <ErrorBanner message={readiness.error} />
          ) : !rd ? (
            <Loading />
          ) : (
            <>
              <div className="flex items-end gap-2">
                <span className="text-3xl font-bold text-slate-900">{rd.percent}%</span>
                <span className="pb-1 text-xs text-slate-500">
                  ลงแล้ว {rd.enrolled} / {rd.required} คน · เหลือ {rd.missing} · ไม่ต้องสแกน {rd.exempt}
                </span>
              </div>
              <div className="h-2.5 overflow-hidden rounded bg-slate-100">
                <div className="h-full bg-blue-600" style={{ width: `${rd.percent}%` }} />
              </div>
              <ul className="divide-y divide-slate-100 text-xs">
                {readiness.data!.branches.map((b) => (
                  <li key={b.branch} className="flex items-center justify-between py-1">
                    <span>{b.branch}</span>
                    <span className={b.missing ? "text-slate-700" : "font-semibold text-emerald-700"}>
                      {b.enrolled}/{b.required} {b.missing ? `(ขาด ${b.missing})` : "✓"}
                    </span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      </div>

      {r && r.by_branch.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-2xs">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-[11px] text-slate-600">
              <tr>
                <th className="px-3 py-2">แผนก (วันนี้)</th>
                {TILES.map((x) => (
                  <th key={x.key} className="px-2 py-2 text-center">{label(x.key)}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {r.by_branch.map((b) => (
                <tr key={b.branch}>
                  <td className="px-3 py-1.5 font-semibold">{b.branch}</td>
                  {TILES.map((x) => {
                    const n = cnt(b.counts, x.key);
                    return (
                      <td key={x.key} className={`px-2 py-1.5 text-center ${n ? (x.key === "ABSENT" ? "font-bold text-rose-700" : "") : "text-slate-300"}`}>
                        {n}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <SystemOverview />
    </div>
  );
}
