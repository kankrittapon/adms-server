import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading } from "../components/Status";

export function Audit() {
  const [eventType, setEventType] = useState("");
  const types = useApi((s) => api.auditEventTypes(s), []);
  const { data, loading, error, reload } = useApi(
    (s) => api.auditEvents({ limit: 200, event_type: eventType || undefined }, s),
    [eventType]
  );

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Audit trail (admin)</h1>
      <p className="mb-4 max-w-3xl text-sm text-gray-500">
        Read-only event log from <code>sync_events</code>: authentication (login, failed
        login, logout, password change), operator management, enrollment and mapping actions,
        and rate-limit triggers. Nothing here is modified.
      </p>

      <div className="mb-4 flex items-center gap-3">
        <select
          value={eventType}
          onChange={(e) => setEventType(e.target.value)}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">All event types</option>
          {types.data?.event_types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
        <button
          onClick={reload}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-100"
        >
          Refresh
        </button>
      </div>

      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : (
        <table className="w-full border-collapse bg-white text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-3 py-2">time (UTC)</th>
              <th className="px-3 py-2">event</th>
              <th className="px-3 py-2">ip</th>
              <th className="px-3 py-2">details</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((e) => (
              <tr key={e.id} className="border-b border-gray-100 align-top">
                <td className="whitespace-nowrap px-3 py-2 font-mono text-xs">
                  {e.created_at.replace("T", " ").slice(0, 19)}
                </td>
                <td className="px-3 py-2">
                  <span className="rounded bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-700">
                    {e.event_type}
                  </span>
                </td>
                <td className="px-3 py-2 font-mono text-xs">{e.device_ip ?? "—"}</td>
                <td className="px-3 py-2 text-xs text-gray-600">{e.message ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
