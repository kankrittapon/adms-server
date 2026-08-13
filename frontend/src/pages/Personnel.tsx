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
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Personnel — Human Master</h1>
        <span className="text-sm text-gray-500">{data ? `${data.total} records` : ""}</span>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={(e) => {
            setSearch(e.target.value);
            setPage(0);
          }}
          placeholder="Search name / personnel ID / rank…"
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        />
        <select
          value={scope}
          onChange={(e) => {
            setScope(e.target.value);
            setPage(0);
          }}
          className="rounded border border-gray-300 px-3 py-1.5 text-sm"
        >
          <option value="">All scope</option>
          <option value="true">Production eligible</option>
          <option value="false">Excluded</option>
        </select>
      </div>

      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : (
        <>
          <table className="w-full border-collapse bg-white text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Rank</th>
                <th className="px-3 py-2">Branch</th>
                <th className="px-3 py-2">Scope</th>
                <th className="px-3 py-2">Active</th>
              </tr>
            </thead>
            <tbody>
              {data?.items.map((h) => (
                <tr key={h.employee_id} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="px-3 py-2">
                    <Link to={`/personnel/${h.employee_id}`} className="text-blue-600 hover:underline">
                      {h.display_name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    {h.rank ?? "—"}
                    {h.rank_metadata?.rank_en_abbreviation ? (
                      <span className="ml-1 text-xs text-gray-500">({h.rank_metadata.rank_en_abbreviation})</span>
                    ) : null}
                  </td>
                  <td className="px-3 py-2">{h.branch ?? "—"}</td>
                  <td className="px-3 py-2">
                    <ScopeBadge scope={h.production_scope} />
                  </td>
                  <td className="px-3 py-2">{h.active ? "yes" : "no"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex items-center gap-3 text-sm">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded border border-gray-300 px-3 py-1 disabled:opacity-40"
            >
              Prev
            </button>
            <span className="text-gray-600">
              Page {page + 1} of {Math.max(1, Math.ceil((data?.total ?? 0) / limit))}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={page + 1 >= Math.ceil((data?.total ?? 0) / limit)}
              className="rounded border border-gray-300 px-3 py-1 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </>
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
    <div className="max-w-2xl">
      <h1 className="mb-4 text-xl font-semibold">{data.display_name}</h1>
      <dl className="rounded-lg border border-gray-200 bg-white p-4 text-sm">
        <Row label="employee_id" value={data.employee_id} mono />
        <Row label="personnel_id" value={data.personnel_id ?? "—"} mono />
        <Row label="rank" value={`${data.rank ?? "—"} ${data.rank_metadata?.rank_en ? `(${data.rank_metadata.rank_en})` : ""}`} />
        <Row label="position" value={data.position ?? "—"} />
        <Row label="branch" value={data.branch ?? "—"} />
        <Row label="category" value={data.category ?? "—"} />
        <Row label="scope" value={data.production_scope ? "production" : "excluded"} />
        <Row label="active" value={data.active ? "yes" : "no"} />
        <Row label="source" value={data.source} />
        <Row label="notes" value={data.notes ?? "—"} />
      </dl>
      <div className="mt-4">
        <Link to="/personnel" className="text-sm text-blue-600 hover:underline">
          ← Back to personnel
        </Link>
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex border-b border-gray-100 py-2 last:border-0">
      <dt className="w-36 shrink-0 font-medium text-gray-500">{label}</dt>
      <dd className={mono ? "font-mono text-xs leading-5" : ""}>{value}</dd>
    </div>
  );
}
