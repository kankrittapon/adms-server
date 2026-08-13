import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatusBadge } from "../components/Status";

export function Attendance() {
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
    </div>
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
