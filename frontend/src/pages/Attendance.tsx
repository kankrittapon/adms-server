import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatusBadge } from "../components/Status";

export function Attendance() {
  const { isAdmin } = useAuth();
  const [status, setStatus] = useState("");
  const [limit, setLimit] = useState(50);

  const { data, loading, error } = useApi(
    (s) => api.attendance({ limit, status: status || undefined }, s),
    [status, limit]
  );

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Attendance</h1>
        <div className="flex items-center gap-3">
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded border border-gray-300 px-3 py-1.5 text-sm">
            <option value="">All statuses</option>
            <option value="ON_TIME">ON_TIME</option>
            <option value="LATE">LATE</option>
            <option value="UNKNOWN">UNKNOWN</option>
          </select>
          <select value={limit} onChange={(e) => setLimit(Number(e.target.value))} className="rounded border border-gray-300 px-3 py-1.5 text-sm">
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={200}>200</option>
          </select>
        </div>
      </div>

      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : (
        <table className="w-full border-collapse bg-white text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-3 py-2">id</th>
              <th className="px-3 py-2">scan time (UTC)</th>
              <th className="px-3 py-2">user</th>
              <th className="px-3 py-2">device_user_pk</th>
              <th className="px-3 py-2">employee</th>
              <th className="px-3 py-2">status</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((a) => (
              <tr key={a.id} className="border-b border-gray-100 hover:bg-gray-50">
                <td className="px-3 py-2">
                  <Link to={`/attendance/${a.id}`} className="font-mono text-xs text-blue-600 hover:underline">
                    {a.id}
                  </Link>
                </td>
                <td className="px-3 py-2 font-mono text-xs">{a.scan_time.replace("T", " ").replace("Z", "Z")}</td>
                <td className="px-3 py-2 font-mono text-xs">{a.user_id}</td>
                <td className="px-3 py-2">{a.device_user_pk ?? "—"}</td>
                <td className="px-3 py-2">{a.employee_id ? <span className="font-mono text-xs">{a.employee_id.slice(0, 8)}…</span> : <span className="text-gray-400">unmapped</span>}</td>
                <td className="px-3 py-2">
                  <StatusBadge status={a.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {isAdmin && <ReconciliationSection />}
    </div>
  );
}

function ReconciliationSection() {
  const { data, loading, error } = useApi((s) => api.unattributedAttendance({ limit: 200 }, s), []);

  return (
    <div className="mt-8 rounded border border-gray-200 bg-white p-4">
      <h2 className="mb-1 text-base font-semibold">Reconciliation diagnostics (admin)</h2>
      <p className="mb-3 max-w-3xl text-sm text-gray-500">
        Unattributed attendance rows with per-row reasoning from the canonical temporal resolver.
        Read-only — no row is ever modified here. Identity authority stays with the VERIFIED
        temporal mapping; nothing is attributed before <code>valid_from</code> or to legacy users.
      </p>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : (data?.items.length ?? 0) === 0 ? (
        <p className="text-sm text-gray-500">No unattributed attendance rows.</p>
      ) : (
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-3 py-2">id</th>
              <th className="px-3 py-2">scan time (UTC)</th>
              <th className="px-3 py-2">user</th>
              <th className="px-3 py-2">pk</th>
              <th className="px-3 py-2">classification</th>
              <th className="px-3 py-2">detail</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((a) => (
              <tr key={a.id} className="border-b border-gray-100 align-top">
                <td className="px-3 py-2">
                  <Link to={`/attendance/${a.id}`} className="font-mono text-xs text-blue-600 hover:underline">
                    {a.id}
                  </Link>
                </td>
                <td className="px-3 py-2 font-mono text-xs">{a.scan_time.replace("T", " ").replace("Z", "Z")}</td>
                <td className="px-3 py-2 font-mono text-xs">{a.user_id}</td>
                <td className="px-3 py-2">{a.device_user_pk ?? "—"}</td>
                <td className="px-3 py-2">
                  <ReasoningBadge classification={a.reasoning.classification} />
                </td>
                <td className="px-3 py-2 text-xs text-gray-600">{a.reasoning.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const REASONING_STYLES: Record<string, string> = {
  NO_DEVICE_USER: "bg-gray-100 text-gray-700",
  LEGACY_USER: "bg-amber-100 text-amber-800",
  NO_MAPPING: "bg-blue-100 text-blue-800",
  BEFORE_VALID_FROM: "bg-purple-100 text-purple-800",
  AFTER_VALID_TO: "bg-purple-100 text-purple-800",
  INSIDE_INTERVAL: "bg-red-100 text-red-800",
};

function ReasoningBadge({ classification }: { classification: string }) {
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${REASONING_STYLES[classification] ?? "bg-gray-100 text-gray-700"}`}>
      {classification}
    </span>
  );
}

export function AttendanceDetail() {
  // Route /attendance/:id — single attendance view (currently summary in list).
  return (
    <div>
      <Link to="/attendance" className="text-sm text-blue-600 hover:underline">
        ← Back to attendance
      </Link>
    </div>
  );
}
