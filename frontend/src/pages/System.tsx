import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Badge, ErrorBanner, Loading, StatCard } from "../components/Status";

export function System() {
  const health = useApi((s) => api.health(s), []);
  const ranks = useApi((s) => api.ranks(s), []);

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">System</h1>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {health.loading ? (
          <Loading />
        ) : health.error ? (
          <ErrorBanner message={health.error} />
        ) : health.data ? (
          <>
            <StatCard label="API / DB" value={<Badge tone={health.data.database === "HEALTHY" ? "green" : "red"}>{health.data.database}</Badge>} hint={health.data.status} />
            <StatCard label="MQTT" value={<Badge tone={health.data.mqtt === "HEALTHY" ? "green" : "amber"}>{health.data.mqtt ?? "—"}</Badge>} />
            <StatCard label="Collector state" value={health.data.collector?.state ?? "—"} hint={health.data.collector?.device_connected ? "Device connected" : "unknown"} />
            <StatCard label="Checked at" value={health.data.timestamp ? new Date(health.data.timestamp).toLocaleTimeString() : "—"} />
          </>
        ) : null}
      </div>

      <div className="mt-8">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-500">RTN Rank Reference ({ranks.data?.length ?? 0})</h2>
        {ranks.loading ? (
          <Loading />
        ) : ranks.error ? (
          <ErrorBanner message={ranks.error} />
        ) : (
          <table className="w-full border-collapse bg-white text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="px-3 py-2">Thai</th>
                <th className="px-3 py-2">English</th>
                <th className="px-3 py-2">Abbr</th>
                <th className="px-3 py-2">Category</th>
              </tr>
            </thead>
            <tbody>
              {ranks.data?.map((r) => (
                <tr key={r.rank_th_abbreviation} className="border-b border-gray-100">
                  <td className="px-3 py-2">
                    {r.rank_th_full} <span className="text-gray-400">({r.rank_th_abbreviation})</span>
                  </td>
                  <td className="px-3 py-2">{r.rank_en}</td>
                  <td className="px-3 py-2 font-mono text-xs">{r.rank_en_abbreviation}</td>
                  <td className="px-3 py-2">{r.rank_category}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
