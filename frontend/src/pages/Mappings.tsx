import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatusBadge } from "../components/Status";

export function Mappings() {
  const { data, loading, error } = useApi((s) => api.mappings({ limit: 100 }, s), []);

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Mapping</h1>
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : (
        <table className="w-full border-collapse bg-white text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-3 py-2">mapping_id</th>
              <th className="px-3 py-2">Human</th>
              <th className="px-3 py-2">device_user</th>
              <th className="px-3 py-2">status</th>
              <th className="px-3 py-2">valid_from</th>
              <th className="px-3 py-2">valid_to</th>
              <th className="px-3 py-2">method</th>
              <th className="px-3 py-2">verified_by</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((m) => (
              <tr key={m.mapping_id} className="border-b border-gray-100">
                <td className="px-3 py-2 font-mono text-xs">{m.mapping_id}</td>
                <td className="px-3 py-2">{m.employee_name ?? m.employee_id.slice(0, 8)}</td>
                <td className="px-3 py-2 font-mono text-xs">{m.device_user_id ?? m.device_user_pk}</td>
                <td className="px-3 py-2">
                  <StatusBadge status={m.mapping_status} />
                </td>
                <td className="px-3 py-2 font-mono text-xs">{m.valid_from.replace("T", " ").replace("Z", "Z")}</td>
                <td className="px-3 py-2 font-mono text-xs">{m.valid_to ? m.valid_to.replace("T", " ").replace("Z", "Z") : "—"}</td>
                <td className="px-3 py-2">{m.verification_method}</td>
                <td className="px-3 py-2">{m.verified_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
