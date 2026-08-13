import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatusBadge } from "../components/Status";

export function Devices() {
  const devices = useApi((s) => api.devices(s), []);
  const users = useApi((s) => api.deviceUsers({ limit: 100 }, s), []);

  if (devices.loading || users.loading) return <Loading />;
  if (devices.error) return <ErrorBanner message={devices.error} />;
  if (users.error) return <ErrorBanner message={users.error} />;

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Devices</h1>
      {devices.data?.items.map((d) => (
        <div key={d.device_id} className="mb-6 rounded-lg border border-gray-200 bg-white p-4 text-sm">
          <div className="flex items-center justify-between">
            <div className="font-semibold">{d.device_name}</div>
            <StatusBadge status={d.active ? "HEALTHY" : "INACTIVE"} />
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2 text-gray-600 md:grid-cols-4">
            <div><span className="text-gray-400">serial</span> {d.serial_number}</div>
            <div><span className="text-gray-400">ip</span> {d.device_ip}</div>
            <div><span className="text-gray-400">platform</span> {d.platform}</div>
            <div><span className="text-gray-400">firmware</span> {d.firmware_version ?? "—"}</div>
          </div>
        </div>
      ))}

      <h2 className="mb-2 mt-6 text-sm font-semibold uppercase tracking-wide text-gray-500">
        Device Users ({users.data?.total ?? 0})
      </h2>
      <table className="w-full border-collapse bg-white text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
            <th className="px-3 py-2">pk</th>
            <th className="px-3 py-2">user_id</th>
            <th className="px-3 py-2">uid</th>
            <th className="px-3 py-2">display name</th>
            <th className="px-3 py-2">privilege</th>
            <th className="px-3 py-2">state</th>
            <th className="px-3 py-2">incarn.</th>
            <th className="px-3 py-2">last seen</th>
          </tr>
        </thead>
        <tbody>
          {users.data?.items.map((u) => (
            <tr key={u.device_user_pk} className="border-b border-gray-100">
              <td className="px-3 py-2 font-mono text-xs">{u.device_user_pk}</td>
              <td className="px-3 py-2 font-mono text-xs">{u.device_user_id}</td>
              <td className="px-3 py-2">{u.device_uid ?? "—"}</td>
              <td className="px-3 py-2">{u.device_display_name ?? "—"}</td>
              <td className="px-3 py-2">{u.privilege}</td>
              <td className="px-3 py-2">
                {u.active ? <StatusBadge status="HEALTHY" /> : <StatusBadge status="INACTIVE" />}
                {u.inactive_at ? <span className="ml-1 text-xs text-gray-400">since {fmt(u.inactive_at)}</span> : null}
              </td>
              <td className="px-3 py-2">
                {u.account_incarnation > 1 ? (
                  <span className="font-semibold text-amber-600">{u.account_incarnation}</span>
                ) : (
                  <span className="text-gray-500">{u.account_incarnation}</span>
                )}
              </td>
              <td className="px-3 py-2 text-xs text-gray-500">{u.roster_last_seen_at ? fmt(u.roster_last_seen_at) : "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function fmt(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
