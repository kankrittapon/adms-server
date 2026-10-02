import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { ErrorBanner, Loading } from "../components/Status";
import { useApi } from "../hooks/useApi";
import { useTranslation } from "../i18n";
import { friendlyApiError } from "../i18n/apiErrors";
import { todayLocal } from "./Absences";

const CODES: Record<string, { code: string; cls: string }> = {
  PRESENT: { code: "ม", cls: "text-emerald-700" },
  LATE: { code: "ส", cls: "bg-orange-100 text-orange-800 font-bold" },
  LEAVE: { code: "ล", cls: "bg-amber-100 text-amber-800" },
  DUTY: { code: "ร", cls: "bg-sky-100 text-sky-800" },
  EXEMPT: { code: "ย", cls: "text-purple-600" },
  NOT_YET: { code: "", cls: "" },
  ABSENT: { code: "ข", cls: "bg-rose-100 text-rose-700 font-bold" },
  OFF: { code: "", cls: "bg-slate-100" },
};
const TOTALS = ["PRESENT", "LATE", "LEAVE", "DUTY", "ABSENT"] as const;

/** One month at a glance — a row per person, a cell per day — with the
 * same rules as the daily roster, plus an Excel-ready export. */
export function MonthlyReport() {
  const { t } = useTranslation();
  const [month, setMonth] = useState(todayLocal().slice(0, 7));
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const report = useApi((s) => api.monthlyReport(month, s), [month]);
  const label = (s: string) => t.leave[`st_${s}` as "st_PRESENT"];

  async function exportCsv() {
    setExporting(true);
    setExportError(null);
    try {
      const blob = await api.monthlyReportCsv(month);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `attendance_${month}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(friendlyApiError(err, t));
    } finally {
      setExporting(false);
    }
  }

  const data = report.data;

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.leave.monthlyTitle}</h1>
          {data && (
            <p className="text-xs text-slate-500">
              {t.leave.monthlySubtitle.replace("{n}", String(data.workdays)).replace("{time}", data.late_after)}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            type="month"
            value={month}
            onChange={(e) => e.target.value && setMonth(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs"
          />
          <button
            type="button"
            onClick={exportCsv}
            disabled={exporting}
            className="rounded-md bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 disabled:opacity-50"
          >
            {t.leave.exportExcel}
          </button>
        </div>
      </div>

      {exportError && <ErrorBanner message={exportError} />}

      <div className="flex flex-wrap gap-3 text-[11px] text-slate-600">
        <span className="font-bold">{t.leave.legend}:</span>
        {Object.entries(CODES)
          .filter(([, v]) => v.code)
          .map(([k, v]) => (
            <span key={k}>
              <span className={`inline-block w-5 rounded text-center ${v.cls}`}>{v.code}</span> {label(k)}
            </span>
          ))}
      </div>

      {report.loading && !data ? (
        <Loading />
      ) : report.error ? (
        <ErrorBanner message={report.error} />
      ) : data ? (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-2xs">
          <table className="border-collapse text-left text-[11px]">
            <thead>
              <tr className="bg-slate-50">
                <th className="sticky left-0 z-10 min-w-[180px] bg-slate-50 px-2 py-1.5">{t.leave.person}</th>
                <th className="px-2 py-1.5">{t.leave.branch}</th>
                {data.days.map((d) => (
                  <th
                    key={String(d.date)}
                    title={d.holiday_name ?? undefined}
                    className={`w-6 px-0.5 py-1.5 text-center ${d.is_workday ? "" : "bg-slate-100 text-slate-400"}`}
                  >
                    {Number(String(d.date).slice(8, 10))}
                  </th>
                ))}
                {TOTALS.map((s) => (
                  <th key={s} className="px-1.5 py-1.5 text-center">
                    {label(s)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.people.map((p) => (
                <tr key={p.employee_id} className="hover:bg-slate-50/70">
                  <td className="sticky left-0 z-10 bg-white px-2 py-1">
                    <Link to={`/personnel/${p.employee_id}`} className="font-semibold text-blue-600 hover:underline">
                      {p.rank ? `${p.rank} ` : ""}
                      {p.display_name}
                    </Link>
                  </td>
                  <td className="px-2 py-1 text-slate-600">{p.branch ?? "—"}</td>
                  {p.days.map((s, i) => (
                    <td key={i} className={`px-0.5 py-1 text-center ${CODES[s]?.cls ?? ""}`}>
                      {CODES[s]?.code ?? ""}
                    </td>
                  ))}
                  {TOTALS.map((s) => {
                    const n = (p.counts as Record<string, number>)[s] ?? 0;
                    return (
                      <td key={s} className={`px-1.5 py-1 text-center ${n ? "font-bold" : "text-slate-300"}`}>
                        {n}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
