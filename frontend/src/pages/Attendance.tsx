import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth";
import { useApi } from "../hooks/useApi";
import { useAttendanceStream } from "../hooks/useAttendanceStream";
import { ErrorBanner, Loading, StatusBadge, StreamStatusBadge } from "../components/Status";
import { useTranslation } from "../i18n";
import { attendanceReasoningLabels, enumLabel } from "../i18n/enumLabels";

/** Primary display in Thailand local time (fixed UTC+7, no DST); storage
 * and the API contract remain UTC/ISO-8601, this is a display-only
 * conversion. Raw UTC stays available via the title tooltip. */
function formatBangkokTime(iso: string): string {
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Bangkok",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    })
      .format(new Date(iso))
      .replace(",", "");
  } catch {
    return iso;
  }
}

export function Attendance() {
  const { isAdmin } = useAuth();
  const { t } = useTranslation();
  const [status, setStatus] = useState("");
  const [limit, setLimit] = useState(50);

  const { data, loading, error, reload } = useApi(
    (s) => api.attendance({ limit, status: status || undefined }, s),
    [status, limit]
  );

  // Realtime: live indicator + auto-refresh when a new scan arrives.
  const { status: streamStatus, lastEvent, reconnect } = useAttendanceStream();
  const [newScan, setNewScan] = useState<{ user_id: string; scan_time: string } | null>(null);
  const bannerTimer = useRef<number | null>(null);
  useEffect(() => {
    if (lastEvent && lastEvent.event_type === "ATTENDANCE_SCAN") {
      setNewScan({ user_id: lastEvent.user_id, scan_time: lastEvent.scan_time });
      reload();
      if (bannerTimer.current) window.clearTimeout(bannerTimer.current);
      bannerTimer.current = window.setTimeout(() => setNewScan(null), 6000);
    }
  }, [lastEvent, reload]);

  return (
    <div className="space-y-5">
      {/* Header & Controls */}
      <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.attendance.title}</h1>
          <p className="text-xs text-slate-500">{t.attendance.subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <StreamStatusBadge status={streamStatus} onRetry={reconnect} />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
            <option value="">{t.common.all}</option>
            <option value="ON_TIME">{t.attendance.onTime} (ON_TIME)</option>
            <option value="LATE">{t.attendance.late} (LATE)</option>
            <option value="UNKNOWN">{t.attendance.unknown} (UNKNOWN)</option>
          </select>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
            <option value={25}>25 rows</option>
            <option value={50}>50 rows</option>
            <option value={200}>200 rows</option>
          </select>
          <button
            onClick={() => reload()}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 hover:text-slate-900"
          >
            {t.common.refresh}
          </button>
        </div>
      </div>

      {/* New Scan Realtime Banner */}
      {newScan && (
        <div className="flex items-center justify-between rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-xs text-emerald-900 shadow-2xs animate-pulse">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-600" />
            <span>
              <strong>{t.attendance.liveStreamBadge}:</strong> Terminal User <strong>{newScan.user_id}</strong> @{" "}
              <code className="font-mono text-xs" title={`${newScan.scan_time} (UTC)`}>{formatBangkokTime(newScan.scan_time)}</code>
            </span>
          </div>
          <button
            onClick={() => reload()}
            className="rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-bold text-white shadow-xs hover:bg-emerald-700"
          >
            {t.common.refresh}
          </button>
        </div>
      )}

      {/* Main Attendance Table */}
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xs">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs table-dense">
              <thead>
                <tr>
                  <th className="w-16">Log ID</th>
                  <th>
                    {t.attendance.timeColumn} <span className="font-normal text-slate-400">({t.attendance.timeColumnSuffix})</span>
                  </th>
                  <th>{t.attendance.terminalIdColumn}</th>
                  <th>Device User PK</th>
                  <th>{t.attendance.personColumn}</th>
                  <th>{t.attendance.statusColumn}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data?.items.map((a) => (
                  <tr key={a.id} className="transition-colors hover:bg-slate-50/80">
                    <td className="font-mono font-bold text-blue-600">
                      <Link to={`/attendance/${a.id}`} className="hover:underline">
                        #{a.id}
                      </Link>
                    </td>
                    <td className="font-mono text-slate-700 whitespace-nowrap" title={`${a.scan_time} (UTC)`}>
                      {formatBangkokTime(a.scan_time)}
                    </td>
                    <td className="font-mono font-semibold text-slate-900">{a.user_id}</td>
                    <td className="font-mono text-slate-500">{a.device_user_pk ?? "—"}</td>
                    <td>
                      {a.employee_id ? (
                        <span className="font-semibold text-slate-900">
                          {a.employee_id.slice(0, 8)}…
                        </span>
                      ) : (
                        <span className="inline-block rounded bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-500">
                          (Unmapped User)
                        </span>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={a.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-2 text-[11px] text-slate-500">
            {t.common.showing} {data?.items.length ?? 0} {t.common.of} {data?.total ?? 0} {t.common.results}
          </div>
        </div>
      )}

      {isAdmin && <ReconciliationSection />}
    </div>
  );
}

function ReconciliationSection() {
  const { t } = useTranslation();
  const { data, loading, error } = useApi((s) => api.unattributedAttendance({ limit: 200 }, s), []);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
      <div className="border-b border-slate-100 pb-3">
        <h2 className="text-sm font-bold text-slate-900">{t.attendance.reconciliationTitle}</h2>
        <p className="mt-0.5 max-w-3xl text-xs text-slate-500 leading-relaxed">
          {t.attendance.reconciliationDesc}
        </p>
      </div>

      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : (data?.items.length ?? 0) === 0 ? (
        <p className="text-xs text-slate-500">No unattributed attendance rows found in current range.</p>
      ) : (
        <div className="overflow-x-auto rounded border border-slate-200">
          <table className="w-full border-collapse text-left text-xs table-dense">
            <thead>
              <tr>
                <th className="w-16">Log ID</th>
                <th>Scan Time ({t.attendance.timeColumnSuffix})</th>
                <th>Terminal User</th>
                <th>Device User PK</th>
                <th>Temporal Classification</th>
                <th>Diagnostic Detail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data?.items.map((a) => (
                <tr key={a.id} className="align-top hover:bg-slate-50/80">
                  <td className="font-mono font-bold text-blue-600">
                    <Link to={`/attendance/${a.id}`} className="hover:underline">
                      #{a.id}
                    </Link>
                  </td>
                  <td className="font-mono text-slate-700 whitespace-nowrap" title={`${a.scan_time} (UTC)`}>
                    {formatBangkokTime(a.scan_time)}
                  </td>
                  <td className="font-mono font-semibold text-slate-900">{a.user_id}</td>
                  <td className="font-mono text-slate-500">{a.device_user_pk ?? "—"}</td>
                  <td>
                    <ReasoningBadge classification={a.reasoning.classification} />
                  </td>
                  <td className="text-slate-600 leading-relaxed">{a.reasoning.detail}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const REASONING_STYLES: Record<string, string> = {
  NO_DEVICE_USER: "bg-slate-100 text-slate-700 border-slate-300",
  LEGACY_USER: "bg-amber-100 text-amber-800 border-amber-300",
  NO_MAPPING: "bg-blue-100 text-blue-800 border-blue-300",
  BEFORE_VALID_FROM: "bg-purple-100 text-purple-800 border-purple-300",
  AFTER_VALID_TO: "bg-purple-100 text-purple-800 border-purple-300",
  INSIDE_INTERVAL: "bg-rose-100 text-rose-800 border-rose-300",
};

function ReasoningBadge({ classification }: { classification: string }) {
  const { locale } = useTranslation();
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-[11px] font-semibold ${
        REASONING_STYLES[classification] ?? "bg-slate-100 text-slate-700 border-slate-300"
      }`}
    >
      {enumLabel(attendanceReasoningLabels, classification, locale)}
    </span>
  );
}

export function AttendanceDetail() {
  const { t } = useTranslation();
  return (
    <div className="space-y-4">
      <Link to="/attendance" className="text-xs font-semibold text-blue-600 hover:underline">
        ← {t.common.back} {t.attendance.title}
      </Link>
    </div>
  );
}
