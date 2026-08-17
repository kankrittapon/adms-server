import { useState } from "react";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading } from "../components/Status";
import { useTranslation } from "../i18n";

export function Audit() {
  const { t } = useTranslation();
  const [eventType, setEventType] = useState("");
  const types = useApi((s) => api.auditEventTypes(s), []);
  const { data, loading, error, reload } = useApi(
    (s) => api.auditEvents({ limit: 200, event_type: eventType || undefined }, s),
    [eventType]
  );

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.audit.title}</h1>
          <p className="text-xs text-slate-500">{t.audit.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 shadow-2xs">
            {data ? `${data.total} ${t.audit.title}` : t.common.loading}
          </span>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[240px]">
          <select
            value={eventType}
            onChange={(e) => setEventType(e.target.value)}
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
            <option value="">{t.audit.eventTypeFilter}</option>
            {types.data?.event_types.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
        <button
          onClick={reload}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50"
        >
          {t.common.refresh}
        </button>
      </div>

      {/* Event Table */}
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xs">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs table-dense">
              <thead>
                <tr>
                  <th className="w-44">{t.audit.timestampColumn} (UTC)</th>
                  <th className="w-48">{t.audit.eventTypeColumn}</th>
                  <th className="w-32">Origin IP</th>
                  <th>{t.audit.detailsColumn}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data?.items.map((e) => (
                  <tr key={e.id} className="align-top transition-colors hover:bg-slate-50/80">
                    <td className="font-mono text-slate-700 whitespace-nowrap">
                      {e.created_at.replace("T", " ").slice(0, 19)}
                    </td>
                    <td>
                      <span className="inline-block rounded border border-slate-200 bg-slate-100 px-2 py-0.5 font-mono text-[11px] font-bold text-slate-700">
                        {e.event_type}
                      </span>
                    </td>
                    <td className="font-mono text-slate-500">{e.device_ip ?? "—"}</td>
                    <td className="text-slate-800 leading-relaxed font-sans">{e.message ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-2 text-[11px] text-slate-500">
            {t.common.showing} {data?.items.length ?? 0} {t.common.of} {data?.total ?? 0}
          </div>
        </div>
      )}
    </div>
  );
}
