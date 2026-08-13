import { useState } from "react";
import { api, ApiClientError } from "../api/client";
import { useApi } from "../hooks/useApi";
import { Badge, ErrorBanner, Loading, StatCard } from "../components/Status";

export function System() {
  const health = useApi((s) => api.health(s), []);
  const ranks = useApi((s) => api.ranks(s), []);

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">System</h1>

      <div className="mb-6">
        <ChangePasswordForm />
      </div>

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

function ChangePasswordForm() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  function submit() {
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
          text: `Password changed. ${r.other_tokens_revoked} other session(s) were signed out.`,
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
    <div className="rounded border border-gray-200 bg-white p-4">
      <h2 className="mb-1 text-base font-semibold">Change password</h2>
      <p className="mb-3 text-sm text-gray-500">
        Changing your password signs out all other sessions (this one stays active).
      </p>
      {msg && (
        <div
          className={`mb-3 rounded border px-3 py-2 text-sm ${
            msg.tone === "ok"
              ? "border-green-300 bg-green-50 text-green-800"
              : "border-red-300 bg-red-50 text-red-800"
          }`}
        >
          {msg.text}
        </div>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-xs text-gray-500">
          Current password
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            className="mt-1 w-52 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-900"
          />
        </label>
        <label className="flex flex-col text-xs text-gray-500">
          New password (≥ 12 chars)
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            className="mt-1 w-52 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-900"
          />
        </label>
        <button
          onClick={submit}
          disabled={busy}
          className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "Saving…" : "Change password"}
        </button>
      </div>
    </div>
  );
}
