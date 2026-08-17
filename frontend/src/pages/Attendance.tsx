import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth";
import { useApi } from "../hooks/useApi";
import { useAttendanceStream } from "../hooks/useAttendanceStream";
import { ErrorBanner, Loading, StatusBadge } from "../components/Status";

export function Attendance() {
  const { isAdmin } = useAuth();
  const [status, setStatus] = useState("");
  const [limit, setLimit] = useState(50);

  const { data, loading, error, reload } = useApi(
    (s) => api.attendance({ limit, status: status || undefined }, s),
    [status, limit]
  );

  // Realtime: live indicator + auto-refresh when a scan arrives via SSE.
  const { status: streamStatus, lastEvent } = useAttendanceStream();
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
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Attendance Monitoring</h1>
          <p className="text-xs text-slate-500">
            Realtime biometric attendance stream and verified Human identity event log.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <LiveBadge status={streamStatus} />
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
            <option value="">All statuses</option>
            <option value="ON_TIME">ON_TIME</option>
            <option value="LATE">LATE</option>
            <option value="UNKNOWN">UNKNOWN</option>
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
            Refresh
          </button>
        </div>
      </div>

      {/* New Scan Realtime Banner */}
      {newScan && (
        <div className="flex items-center justify-between rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-xs text-emerald-900 shadow-2xs animate-pulse">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-600" />
            <span>
              <strong>Live Scan Detected:</strong> Terminal User <strong>{newScan.user_id}</strong> scanned at{" "}
              <code className="font-mono text-xs">{newScan.scan_time.replace("T", " ")}</code>.
            </span>
          </div>
          <button
            onClick={() => reload()}
            className="rounded-md bg-emerald-600 px-2.5 py-1 text-xs font-bold text-white shadow-xs hover:bg-emerald-700"
          >
            Refresh View
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
                  <th>Scan Time (UTC)</th>
                  <th>Terminal User</th>
                  <th>Device User PK</th>
                  <th>Human Employee Attribution</th>
                  <th>Attendance Status</th>
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
                    <td className="font-mono text-slate-700 whitespace-nowrap">
                      {a.scan_time.replace("T", " ").replace("Z", " UTC")}
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
            Showing {data?.items.length ?? 0} of {data?.total ?? 0} recorded attendance logs.
          </div>
        </div>
      )}

      {isAdmin && <ReconciliationSection />}
    </div>
  );
}

function ReconciliationSection() {
  const { data, loading, error } = useApi((s) => api.unattributedAttendance({ limit: 200 }, s), []);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
      <div className="border-b border-slate-100 pb-3">
        <h2 className="text-sm font-bold text-slate-900">Reconciliation Diagnostics (Admin Only)</h2>
        <p className="mt-0.5 max-w-3xl text-xs text-slate-500 leading-relaxed">
          Unattributed attendance rows with per-row reasoning from the canonical temporal resolver.
          Read-only — no row is modified here. Identity authority stays with the VERIFIED temporal mapping.
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
                <th>Scan Time (UTC)</th>
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
                  <td className="font-mono text-slate-700 whitespace-nowrap">
                    {a.scan_time.replace("T", " ").replace("Z", " UTC")}
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
  return (
    <span
      className={`inline-block rounded border px-2 py-0.5 text-[11px] font-semibold ${
        REASONING_STYLES[classification] ?? "bg-slate-100 text-slate-700 border-slate-300"
      }`}
    >
      {classification}
    </span>
  );
}

function LiveBadge({ status }: { status: "connecting" | "connected" | "disconnected" }) {
  const styles: Record<string, string> = {
    connected: "bg-emerald-50 text-emerald-700 border-emerald-300",
    connecting: "bg-amber-50 text-amber-700 border-amber-300",
    disconnected: "bg-slate-100 text-slate-500 border-slate-300",
  };
  const labels: Record<string, string> = {
    connected: "LIVE STREAM ACTIVE",
    connecting: "CONNECTING...",
    disconnected: "STREAM OFFLINE",
  };
  return (
    <span
      title={"Realtime stream via MQTT→SSE"}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold ${
        styles[status] ?? styles.disconnected
      }`}
    >
      <span
        className={`inline-block h-2 w-2 rounded-full ${
          status === "connected" ? "animate-pulse bg-emerald-500" : "bg-current opacity-50"
        }`}
      />
      {labels[status] ?? "STREAM OFFLINE"}
    </span>
  );
}

export function AttendanceDetail() {
  return (
    <div className="space-y-4">
      <Link to="/attendance" className="text-xs font-semibold text-blue-600 hover:underline">
        ← Back to Attendance Monitor
      </Link>
    </div>
  );
}
