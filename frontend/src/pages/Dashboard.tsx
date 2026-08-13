import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatCard } from "../components/Status";

export function Dashboard() {
  const { data, loading, error } = useApi((s) => api.dashboard(s), []);

  if (loading) return <Loading />;
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <ErrorBanner message="No dashboard data" />;

  const enrollStatus = Object.entries(data.enrollments_by_status ?? {});

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Dashboard</h1>
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Humans" value={data.humans_total} hint={`${data.humans_production_eligible} eligible / ${data.humans_excluded} excluded`} />
        <StatCard label="Devices" value={data.devices_total} hint={`${data.devices_active} active`} />
        <StatCard label="Device Users" value={data.device_users_total} hint={`${data.device_users_active} active`} />
        <StatCard label="Attendance" value={data.attendance_total} hint={`${data.attendance_today} today · ${data.attendance_unattributed} unattributed`} />
        <StatCard label="Mappings" value={data.mappings_total} hint={`${data.mappings_verified_active} VERIFIED active`} />
        <StatCard label="Collector" value={data.collector?.state ?? "—"} hint={data.collector?.device_connected ? "Device connected" : "No collector heartbeat"} />
      </div>
      {enrollStatus.length > 0 && (
        <div className="mt-6 rounded-lg border border-gray-200 bg-white p-4">
          <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">Enrollments by status</h2>
          <div className="flex flex-wrap gap-3">
            {enrollStatus.map(([k, v]) => (
              <div key={k} className="rounded border border-gray-200 px-3 py-1.5 text-sm">
                <span className="font-medium">{k}</span> <span className="text-gray-500">{v}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
