import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatusBadge } from "../components/Status";

export function Enrollments() {
  const { data, loading, error } = useApi((s) => api.enrollments({ limit: 100 }, s), []);

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Enrollment</h1>
      <p className="mb-4 max-w-3xl text-sm text-gray-500">
        Read-only view of the controlled enrollment state machine. Operator write actions (reserve,
        fingerprint confirmation, controlled scan) are gated behind <code>API_WRITE_ENABLED</code> and
        are NOT exposed in F2.
      </p>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : (
        <table className="w-full border-collapse bg-white text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-3 py-2">id</th>
              <th className="px-3 py-2">Human</th>
              <th className="px-3 py-2">terminal id</th>
              <th className="px-3 py-2">status</th>
              <th className="px-3 py-2">reserved_by</th>
              <th className="px-3 py-2">controlled scan</th>
              <th className="px-3 py-2">confirmed_by</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((e) => (
              <tr key={e.enrollment_id} className="border-b border-gray-100">
                <td className="px-3 py-2 font-mono text-xs">{e.enrollment_id}</td>
                <td className="px-3 py-2">{e.employee_name ?? e.employee_id.slice(0, 8)}</td>
                <td className="px-3 py-2 font-mono text-xs">{e.reserved_device_user_id}</td>
                <td className="px-3 py-2">
                  <StatusBadge status={e.status} />
                </td>
                <td className="px-3 py-2">{e.reserved_by}</td>
                <td className="px-3 py-2 font-mono text-xs">{e.controlled_scan_time ?? "—"}</td>
                <td className="px-3 py-2">{e.confirmed_by ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
