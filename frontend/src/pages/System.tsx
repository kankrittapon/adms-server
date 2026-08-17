import { useState } from "react";
import { api, ApiClientError } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Badge, ErrorBanner, Loading, StatCard } from "../components/Status";

export function System() {
  const health = useApi((s) => api.health(s), []);
  const ranks = useApi((s) => api.ranks(s), []);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-slate-200 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">System Infrastructure & Health</h1>
        <p className="text-xs text-slate-500">
          Core backend subsystems, database connectivity, MQTT telemetry, and RTN reference metadata.
        </p>
      </div>

      {/* System Telemetry Cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        {health.loading ? (
          <div className="col-span-full">
            <Loading />
          </div>
        ) : health.error ? (
          <div className="col-span-full">
            <ErrorBanner message={health.error} />
          </div>
        ) : health.data ? (
          <>
            <StatCard
              label="API & PostgreSQL DB"
              value={
                <Badge tone={health.data.database === "HEALTHY" ? "green" : "red"}>
                  {health.data.database}
                </Badge>
              }
              hint={`Status: ${health.data.status}`}
            />
            <StatCard
              label="Mosquitto MQTT"
              value={
                <Badge tone={health.data.mqtt === "HEALTHY" ? "green" : "amber"}>
                  {health.data.mqtt ?? "—"}
                </Badge>
              }
              hint="Internal event bus"
            />
            <StatCard
              label="Collector State"
              value={health.data.collector?.state ?? "—"}
              hint={health.data.collector?.device_connected ? "Device connected (LIVE)" : "Device disconnected"}
              tone={health.data.collector?.device_connected ? "highlight" : "normal"}
            />
            <StatCard
              label="Telemetry Timestamp"
              value={health.data.timestamp ? new Date(health.data.timestamp).toLocaleTimeString() : "—"}
              hint={health.data.timestamp ? new Date(health.data.timestamp).toLocaleDateString() : ""}
            />
          </>
        ) : null}
      </div>

      {/* Operator Security Section */}
      <ChangePasswordForm />

      {/* RTN Rank Reference Table */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between border-b border-slate-200 pb-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Royal Thai Navy Rank Reference ({ranks.data?.length ?? 0})
          </h2>
          <span className="text-[11px] text-slate-400">Canonical Display Metadata</span>
        </div>

        {ranks.loading ? (
          <Loading />
        ) : ranks.error ? (
          <ErrorBanner message={ranks.error} />
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xs">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs table-dense">
                <thead>
                  <tr>
                    <th>Thai Full Rank</th>
                    <th>Thai Abbreviation</th>
                    <th>English Rank</th>
                    <th>English Abbr</th>
                    <th>Rank Category</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {ranks.data?.map((r) => (
                    <tr key={r.rank_th_abbreviation} className="transition-colors hover:bg-slate-50/80">
                      <td className="font-semibold text-slate-900">{r.rank_th_full}</td>
                      <td>
                        <span className="font-mono text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded text-[11px]">
                          {r.rank_th_abbreviation}
                        </span>
                      </td>
                      <td className="text-slate-800">{r.rank_en}</td>
                      <td className="font-mono text-slate-600 text-[11px]">{r.rank_en_abbreviation}</td>
                      <td>
                        <span className="inline-block rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-700">
                          {r.rank_category}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ChangePasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!current || next.length < 12) {
      setMsg({ tone: "err", text: "Enter your current password and a new password of at least 12 characters." });
      return;
    }
    setBusy(true);
    setMsg(null);
    api
      .changePassword(current, next)
      .then((r) => {
        setCurrent("");
        setNext("");
        setMsg({
          tone: "ok",
          text: `Password changed successfully. ${r.other_tokens_revoked} other session(s) were revoked.`,
        });
      })
      .catch((e: unknown) => {
        if (e instanceof ApiClientError) {
          setMsg({ tone: "err", text: `${e.code}: ${e.message}` });
        } else {
          setMsg({ tone: "err", text: e instanceof Error ? e.message : String(e) });
        }
      })
      .finally(() => setBusy(false));
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
      <div className="border-b border-slate-100 pb-3">
        <h2 className="text-sm font-bold text-slate-900">Operator Account Security</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Changing your password signs out all other active sessions (this current session stays authenticated).
        </p>
      </div>

      {msg && (
        <div
          className={`rounded-md border p-3 text-xs font-medium ${
            msg.tone === "ok"
              ? "border-emerald-300 bg-emerald-50 text-emerald-900"
              : "border-rose-300 bg-rose-50 text-rose-900"
          }`}
        >
          {msg.text}
        </div>
      )}

      <form onSubmit={submit} className="flex flex-wrap items-end gap-3 pt-1">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
            Current Password
          </label>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            disabled={busy}
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100"
          />
        </div>

        <div className="flex-1 min-w-[200px]">
          <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
            New Password (≥ 12 characters)
          </label>
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            disabled={busy}
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100"
          />
        </div>

        <div>
          <button
            type="submit"
            disabled={busy || !current || next.length < 12}
            className="rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-600 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
          >
            {busy ? "Updating..." : "Update Password"}
          </button>
        </div>
      </form>
    </div>
  );
}
