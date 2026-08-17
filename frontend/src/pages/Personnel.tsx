import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, ScopeBadge } from "../components/Status";

export function Personnel() {
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState<string>("");
  const [page, setPage] = useState(0);
  const limit = 25;

  const { data, loading, error } = useApi(
    (s) =>
      api.humans(
        {
          limit,
          offset: page * limit,
          search: search || undefined,
          production_scope: scope === "true" ? true : scope === "false" ? false : undefined,
        },
        s
      ),
    [search, scope, page]
  );

  return (
    <div className="space-y-5">
      {/* Header & Filter Controls */}
      <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Personnel — Human Master</h1>
          <p className="text-xs text-slate-500">
            Authoritative human identities imported from official Navy personnel rosters.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 shadow-2xs">
            {data ? `${data.total} Total Records` : "Loading..."}
          </span>
        </div>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[240px]">
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            placeholder="Search name, personnel ID, or RTN rank..."
            className="w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          />
        </div>
        <div>
          <select
            value={scope}
            onChange={(e) => {
              setScope(e.target.value);
              setPage(0);
            }}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
            <option value="">All Scopes</option>
            <option value="true">Production Eligible Only</option>
            <option value="false">Excluded Personnel</option>
          </select>
        </div>
      </div>

      {/* Main Table */}
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
                  <th>Full Name & Identity</th>
                  <th>RTN Rank</th>
                  <th>Branch / Division</th>
                  <th>Production Scope</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data?.items.map((h) => (
                  <tr key={h.employee_id} className="transition-colors hover:bg-slate-50/80">
                    <td>
                      <Link
                        to={`/personnel/${h.employee_id}`}
                        className="font-bold text-blue-600 hover:underline"
                      >
                        {h.display_name}
                      </Link>
                    </td>
                    <td>
                      <span className="font-medium text-slate-800">{h.rank ?? "—"}</span>
                      {h.rank_metadata?.rank_en_abbreviation ? (
                        <span className="ml-1 text-[11px] text-slate-500">
                          ({h.rank_metadata.rank_en_abbreviation})
                        </span>
                      ) : null}
                    </td>
                    <td className="text-slate-600">{h.branch ?? "—"}</td>
                    <td>
                      <ScopeBadge scope={h.production_scope} />
                    </td>
                    <td>
                      {h.active ? (
                        <span className="inline-flex items-center gap-1 font-semibold text-emerald-700">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                          Active
                        </span>
                      ) : (
                        <span className="text-slate-400">Inactive</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Bar */}
          <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/60 px-4 py-2.5 text-xs text-slate-600">
            <div>
              Showing {page * limit + 1}–{Math.min((page + 1) * limit, data?.total ?? 0)} of {data?.total ?? 0}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <span className="font-medium text-slate-700">
                Page {page + 1} of {Math.max(1, Math.ceil((data?.total ?? 0) / limit))}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page + 1 >= Math.ceil((data?.total ?? 0) / limit)}
                className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export function HumanDetail() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const { data, loading, error } = useApi((s) => api.human(employeeId as string, s), [employeeId]);

  if (loading) return <Loading />;
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <ErrorBanner message="Human not found" />;

  return (
    <div className="max-w-2xl space-y-4">
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{data.display_name}</h1>
          <p className="text-xs text-slate-500">Personnel Master Profile</p>
        </div>
        <ScopeBadge scope={data.production_scope} />
      </div>

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xs">
        <dl className="divide-y divide-slate-100 text-xs">
          <Row label="Employee ID (UUID)" value={data.employee_id} mono />
          <Row label="Personnel ID" value={data.personnel_id ?? "—"} mono />
          <Row
            label="RTN Rank"
            value={`${data.rank ?? "—"} ${data.rank_metadata?.rank_en ? `(${data.rank_metadata.rank_en})` : ""}`}
          />
          <Row label="Position" value={data.position ?? "—"} />
          <Row label="Branch" value={data.branch ?? "—"} />
          <Row label="Category" value={data.category ?? "—"} />
          <Row label="Production Scope" value={data.production_scope ? "Production Eligible" : "Excluded"} />
          <Row label="Active Status" value={data.active ? "Active" : "Inactive"} />
          <Row label="Roster Source" value={data.source} />
          <Row label="Internal Notes" value={data.notes ?? "—"} />
        </dl>
      </div>

      <div>
        <Link to="/personnel" className="text-xs font-semibold text-blue-600 hover:underline">
          ← Back to Personnel Master
        </Link>
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center px-4 py-2.5">
      <dt className="w-44 shrink-0 font-bold uppercase text-[10px] text-slate-400">{label}</dt>
      <dd className={`text-slate-900 ${mono ? "font-mono text-[11px]" : ""}`}>{value}</dd>
    </div>
  );
}
