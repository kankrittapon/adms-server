import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatusBadge } from "../components/Status";
import { useTranslation } from "../i18n";

export function Devices() {
  const { t } = useTranslation();
  const devices = useApi((s) => api.devices(s), []);
  const users = useApi((s) => api.deviceUsers({ limit: 100 }, s), []);

  if (devices.loading || users.loading) return <Loading />;
  if (devices.error) return <ErrorBanner message={devices.error} />;
  if (users.error) return <ErrorBanner message={users.error} />;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col justify-between gap-2 border-b border-slate-200 pb-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.devices.title}</h1>
          <p className="text-xs text-slate-500">{t.devices.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 shadow-2xs">
            {devices.data?.items.length ?? 0} {t.nav.devices}
          </span>
        </div>
      </div>

      {/* Terminal Cards */}
      <div className="grid grid-cols-1 gap-4">
        {devices.data?.items.map((d) => (
          <div
            key={d.device_id}
            className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3"
          >
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="flex h-7 w-7 items-center justify-center rounded-md bg-blue-50 font-bold text-blue-700 text-xs border border-blue-200">
                  ZK
                </div>
                <div>
                  <div className="font-bold text-slate-900">{d.device_name}</div>
                  <div className="text-[11px] text-slate-500 font-mono">ID #{d.device_id}</div>
                </div>
              </div>
              <StatusBadge status={d.active ? "LIVE" : "INACTIVE"} />
            </div>

            <div className="grid grid-cols-2 gap-4 text-xs md:grid-cols-4 pt-1">
              <div>
                <span className="block text-[10px] font-bold uppercase text-slate-400">{t.devices.deviceIp}</span>
                <span className="font-mono font-semibold text-slate-800">{d.device_ip}:4370</span>
              </div>
              <div>
                <span className="block text-[10px] font-bold uppercase text-slate-400">{t.devices.serial}</span>
                <span className="font-mono text-slate-800">{d.serial_number}</span>
              </div>
              <div>
                <span className="block text-[10px] font-bold uppercase text-slate-400">{t.devices.platform}</span>
                <span className="text-slate-800 font-medium">{d.platform}</span>
              </div>
              <div>
                <span className="block text-[10px] font-bold uppercase text-slate-400">{t.devices.firmware}</span>
                <span className="font-mono text-slate-800">{d.firmware_version ?? "—"}</span>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Device Users Table */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            {t.devices.discoveredUsers} ({users.data?.total ?? 0})
          </h2>
          <span className="text-[11px] text-slate-400">Synced via Collector Roster Ingestion</span>
        </div>

        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xs">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs table-dense">
              <thead>
                <tr>
                  <th className="w-14">PK</th>
                  <th>{t.attendance.terminalIdColumn}</th>
                  <th>Terminal UID</th>
                  <th>Display Name</th>
                  <th>{t.devices.privilege}</th>
                  <th>{t.common.status}</th>
                  <th>{t.devices.incarnation}</th>
                  <th>{t.devices.lastSeen}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {users.data?.items.map((u) => (
                  <tr key={u.device_user_pk} className="transition-colors hover:bg-slate-50/80">
                    <td className="font-mono text-slate-400">#{u.device_user_pk}</td>
                    <td className="font-mono font-bold text-slate-900">{u.device_user_id}</td>
                    <td className="font-mono text-slate-600">{u.device_uid ?? "—"}</td>
                    <td className="font-medium text-slate-800">{u.device_display_name ?? "—"}</td>
                    <td>
                      <span className="inline-block rounded bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-700">
                        {u.privilege}
                      </span>
                    </td>
                    <td>
                      {u.active ? (
                        <StatusBadge status="ACTIVE" />
                      ) : (
                        <span className="text-slate-400">
                          Inactive {u.inactive_at ? `(since ${fmt(u.inactive_at)})` : ""}
                        </span>
                      )}
                    </td>
                    <td>
                      {u.account_incarnation > 1 ? (
                        <span className="inline-block rounded bg-amber-100 px-1.5 py-0.2 font-mono text-[11px] font-bold text-amber-800">
                          v{u.account_incarnation} (Recycled)
                        </span>
                      ) : (
                        <span className="font-mono text-slate-500">v{u.account_incarnation}</span>
                      )}
                    </td>
                    <td className="font-mono text-slate-500 whitespace-nowrap">
                      {u.roster_last_seen_at ? fmt(u.roster_last_seen_at) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
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
