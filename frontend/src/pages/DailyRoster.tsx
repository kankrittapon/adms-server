import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorBanner, Loading } from "../components/Status";
import { useApi } from "../hooks/useApi";
import { useTranslation } from "../i18n";
import { formatThaiDate, todayLocal } from "./Absences";

const STATUS_ORDER = ["PRESENT", "LATE", "LEAVE", "DUTY", "EXEMPT", "NOT_YET", "ABSENT", "NOT_ENROLLED", "OFF"] as const;
type RosterStatus = (typeof STATUS_ORDER)[number];

const STATUS_TONE: Record<RosterStatus, string> = {
  PRESENT: "text-emerald-700 bg-emerald-50 border-emerald-200",
  LATE: "text-orange-700 bg-orange-50 border-orange-200",
  LEAVE: "text-amber-800 bg-amber-50 border-amber-200",
  DUTY: "text-sky-800 bg-sky-50 border-sky-200",
  EXEMPT: "text-purple-700 bg-purple-50 border-purple-200",
  NOT_YET: "text-slate-600 bg-slate-50 border-slate-200",
  NOT_ENROLLED: "text-slate-500 bg-white border-dashed border-slate-300",
  ABSENT: "text-rose-700 bg-rose-50 border-rose-200",
  OFF: "text-slate-500 bg-slate-50 border-slate-200",
};

/** Who is here today, who is on leave or duty, who is late or absent —
 * per section. Computed live from scans + leave records + holidays. */
export function DailyRoster() {
  const { t } = useTranslation();
  const [day, setDay] = useState(todayLocal());
  const [filter, setFilter] = useState<RosterStatus | "">("");
  const roster = useApi((s) => api.dailyRoster(day, s), [day]);
  const label = (s: RosterStatus) => t.leave[`st_${s}` as const];

  const data = roster.data;
  const shown = STATUS_ORDER.filter((s) => s !== "OFF" || (data && !data.is_workday));
  const people = (data?.people ?? []).filter((p) => !filter || p.status === filter);

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.leave.dailyTitle}</h1>
          <p className="text-xs text-slate-500">{t.leave.dailySubtitle
              .replace("{window}", data?.scan_window ?? "06:30–11:00")
              .replace("{time}", data?.late_after ?? "10:00")}</p>
        </div>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={day}
            onChange={(e) => e.target.value && setDay(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs"
          />
          <button
            type="button"
            onClick={() => setDay(todayLocal())}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            {t.leave.today}
          </button>
          <button
            type="button"
            onClick={() => roster.reload()}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            {t.common.refresh}
          </button>
        </div>
      </div>

      {roster.loading && !data ? (
        <Loading />
      ) : roster.error ? (
        <ErrorBanner message={roster.error} />
      ) : data ? (
        <>
          {!data.is_workday && (
            <div className="rounded-lg border border-slate-200 bg-slate-100 px-4 py-2 text-xs font-semibold text-slate-700">
              {t.leave.holidayBadge}
              {data.holiday_name ? ` — ${data.holiday_name}` : ""} · {formatThaiDate(String(data.date))}
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-8">
            <button
              type="button"
              onClick={() => setFilter("")}
              className={`rounded-lg border bg-white p-3 text-left shadow-2xs ${filter === "" ? "ring-1 ring-blue-500 border-blue-500" : "border-slate-200"}`}
            >
              <div className="text-[11px] font-semibold text-slate-500">{t.leave.totalLabel}</div>
              <div className="mt-1 text-2xl font-bold text-slate-900">{data.total}</div>
            </button>
            {shown.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setFilter(filter === s ? "" : s)}
                className={`rounded-lg border p-3 text-left shadow-2xs ${STATUS_TONE[s]} ${filter === s ? "ring-1 ring-blue-500" : ""}`}
              >
                <div className="text-[11px] font-semibold">{label(s)}</div>
                <div className="mt-1 text-2xl font-bold">{(data.totals as Record<string, number>)[s] ?? 0}</div>
              </button>
            ))}
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-2xs">
            <div className="border-b border-slate-100 px-4 py-2 text-xs font-bold uppercase tracking-wider text-slate-500">
              {t.leave.byBranch}
            </div>
            <table className="w-full border-collapse text-left text-xs table-dense">
              <thead>
                <tr>
                  <th>{t.leave.branch}</th>
                  {shown.map((s) => (
                    <th key={s} className="text-center">
                      {label(s)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.by_branch.map((b) => (
                  <tr key={b.branch}>
                    <td className="font-semibold text-slate-800">{b.branch}</td>
                    {shown.map((s) => {
                      const n = (b.counts as Record<string, number>)[s] ?? 0;
                      return (
                        <td key={s} className={`text-center ${n ? "font-bold text-slate-900" : "text-slate-300"}`}>
                          {n}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-2xs">
            <table className="w-full border-collapse text-left text-xs table-dense">
              <thead>
                <tr>
                  <th>{t.leave.person}</th>
                  <th>{t.leave.branch}</th>
                  <th>{t.common.status}</th>
                  <th>{t.leave.firstScan}</th>
                  <th>{t.leave.note}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {people.map((p) => {
                  const st = p.status as RosterStatus;
                  return (
                    <tr key={p.employee_id}>
                      <td>
                        <Link to={`/personnel/${p.employee_id}`} className="font-semibold text-blue-600 hover:underline">
                          {p.rank ? `${p.rank} ` : ""}
                          {p.display_name}
                        </Link>
                      </td>
                      <td className="text-slate-600">{p.branch ?? "—"}</td>
                      <td>
                        <span className={`rounded border px-1.5 py-0.5 text-[11px] font-bold ${STATUS_TONE[st] ?? ""}`}>
                          {label(st)}
                        </span>
                      </td>
                      <td className="font-mono text-[11px]">
                        {p.first_scan
                          ? new Date(p.first_scan).toLocaleTimeString("th-TH", {
                              hour: "2-digit",
                              minute: "2-digit",
                              timeZone: "Asia/Bangkok",
                            })
                          : "—"}
                      </td>
                      <td className="text-slate-600">
                        {p.scans_outside_window > 0 && (
                          <span className="mr-1 rounded bg-slate-100 px-1 text-[10px] font-semibold text-slate-600">
                            {t.workflow.outsideWindow} ×{p.scans_outside_window}
                          </span>
                        )}
                        {p.absence_name_th
                          ? `${p.absence_name_th} ${formatThaiDate(String(p.absence_start))}–${formatThaiDate(
                              String(p.absence_end)
                            )}${p.order_ref ? ` · ${p.order_ref}` : ""}`
                          : ""}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : null}
    </div>
  );
}
