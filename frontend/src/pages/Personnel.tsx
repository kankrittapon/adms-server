import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { ErrorBanner, Loading, ScopeBadge } from "../components/Status";
import { useApi } from "../hooks/useApi";
import { useTranslation } from "../i18n";

export function Personnel() {
  const { t } = useTranslation();
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
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.personnel.title}</h1>
          <p className="text-xs text-slate-500">{t.personnel.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 shadow-2xs">
            {data ? `${data.total} ${t.common.results}` : t.common.loading}
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
            placeholder={t.common.searchPlaceholder}
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
            <option value="">{t.personnel.allScopes}</option>
            <option value="true">{t.personnel.productionScope}</option>
            <option value="false">{t.personnel.excludedScope}</option>
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
                  <th>{t.personnel.thaiName}</th>
                  <th>{t.personnel.englishName}</th>
                  <th>{t.personnel.rank}</th>
                  <th>{t.personnel.branch}</th>
                  <th>{t.personnel.scope}</th>
                  <th>{t.common.status}</th>
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
                    <td className="text-slate-700">
                      {h.english_name ? (
                        <span className="font-medium text-slate-900">{h.english_name}</span>
                      ) : (
                        <span className="text-slate-400 italic text-[11px]">{t.personnel.notSet}</span>
                      )}
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
                          {t.common.active}
                        </span>
                      ) : (
                        <span className="text-slate-400">{t.common.inactive}</span>
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
              {t.common.showing} {page * limit + 1}–{Math.min((page + 1) * limit, data?.total ?? 0)} {t.common.of} {data?.total ?? 0}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(0, p - 1))}
                disabled={page === 0}
                className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t.common.back}
              </button>
              <span className="font-medium text-slate-700">
                {t.common.page} {page + 1} {t.common.of} {Math.max(1, Math.ceil((data?.total ?? 0) / limit))}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page + 1 >= Math.ceil((data?.total ?? 0) / limit)}
                className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {t.common.next}
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
  const { me, canMutate } = useAuth();
  const { t } = useTranslation();
  const { data, loading, error, reload } = useApi((s) => api.human(employeeId as string, s), [employeeId]);

  const [editingEnglish, setEditingEnglish] = useState(false);
  const [englishInput, setEnglishInput] = useState("");
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState(false);

  if (loading) return <Loading />;
  if (error) return <ErrorBanner message={error} />;
  if (!data) return <ErrorBanner message="Human not found" />;

  const isAdmin = me?.role === "ADMIN";

  function startEdit() {
    setEnglishInput(data?.english_name ?? "");
    setEditingEnglish(true);
    setSaveError(null);
    setSaveSuccess(false);
  }

  async function handleSaveEnglish(e: React.FormEvent) {
    e.preventDefault();
    if (!employeeId) return;
    setSaveBusy(true);
    setSaveError(null);
    try {
      await api.updateHumanEnglishName(employeeId, englishInput.trim() || null);
      setSaveSuccess(true);
      setEditingEnglish(false);
      reload();
    } catch (err) {
      if (err instanceof ApiClientError && (err.code === "WRITE_DISABLED" || err.code === "WRITE_SESSION_REQUIRED" || err.code === "WRITE_SESSION_EXPIRED")) {
        setSaveError(t.personnel.writesDisabledNotice);
      } else {
        setSaveError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setSaveBusy(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-4">
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{data.display_name}</h1>
          <p className="text-xs text-slate-500">{t.personnel.subtitle}</p>
        </div>
        <ScopeBadge scope={data.production_scope} />
      </div>

      {saveSuccess && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-xs font-semibold text-emerald-800">
          ✓ {t.personnel.updateSuccess}
        </div>
      )}

      {saveError && (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
          {t.personnel.updateFailed}: {saveError}
        </div>
      )}

      <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xs">
        <dl className="divide-y divide-slate-100 text-xs">
          <Row label={t.personnel.thaiName} value={data.display_name} />

          {/* Editable English Name Row */}
          <div className="flex items-center justify-between px-4 py-2.5">
            <dt className="w-44 shrink-0 font-bold uppercase text-[10px] text-slate-400">
              {t.personnel.englishName}
            </dt>
            <dd className="flex-1 text-slate-900">
              {editingEnglish ? (
                <form onSubmit={handleSaveEnglish} className="flex items-center gap-2">
                  <input
                    type="text"
                    value={englishInput}
                    onChange={(e) => setEnglishInput(e.target.value)}
                    placeholder={t.personnel.englishNamePlaceholder}
                    disabled={saveBusy}
                    className="flex-1 rounded border border-slate-300 px-2 py-1 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
                  />
                  <button
                    type="submit"
                    disabled={saveBusy}
                    className="rounded bg-blue-600 px-2.5 py-1 text-xs font-bold text-white shadow-2xs hover:bg-blue-700 disabled:opacity-50"
                  >
                    {saveBusy ? t.common.saving : t.common.save}
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditingEnglish(false)}
                    disabled={saveBusy}
                    className="rounded border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    {t.common.cancel}
                  </button>
                </form>
              ) : (
                <div className="flex items-center justify-between">
                  <span>
                    {data.english_name ? (
                      <span className="font-semibold">{data.english_name}</span>
                    ) : (
                      <span className="text-slate-400 italic">{t.personnel.notSet}</span>
                    )}
                  </span>
                  {isAdmin && (
                    <button
                      type="button"
                      onClick={startEdit}
                      disabled={!canMutate}
                      title={!canMutate ? t.personnel.writesDisabledNotice : t.personnel.editEnglishName}
                      className="ml-3 rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-blue-600 hover:bg-blue-50 hover:border-blue-200 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {t.common.edit}
                    </button>
                  )}
                </div>
              )}
            </dd>
          </div>

          <Row label={t.personnel.personnelId} value={data.personnel_id ?? "—"} mono />
          <Row
            label={t.personnel.rank}
            value={`${data.rank ?? "—"} ${data.rank_metadata?.rank_en ? `(${data.rank_metadata.rank_en})` : ""}`}
          />
          <Row label={t.personnel.position} value={data.position ?? "—"} />
          <Row label={t.personnel.branch} value={data.branch ?? "—"} />
          <Row label={t.personnel.category} value={data.category ?? "—"} />
          <Row
            label={t.personnel.scope}
            value={data.production_scope ? t.personnel.productionScope : t.personnel.excludedScope}
          />
          <Row label={t.common.status} value={data.active ? t.common.active : t.common.inactive} />
          <Row label="UUID" value={data.employee_id} mono />
        </dl>
      </div>

      <div>
        <Link to="/personnel" className="text-xs font-semibold text-blue-600 hover:underline">
          ← {t.common.back} {t.personnel.title}
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
