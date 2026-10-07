import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { CsvImportModal } from "../components/CsvImportModal";
import { AbsenceTable } from "./Absences";
import { EXEMPT_REASON_PRESETS, EnrollLink, TerminalNameCard, OffboardPanel, ScanPolicyCard } from "../components/PersonnelLifecycle";
import { PersonnelFormModal } from "../components/PersonnelFormModal";
import { ErrorBanner, Loading, ScopeBadge } from "../components/Status";
import { useApi } from "../hooks/useApi";
import type { Human } from "../api/types";
import { useTranslation } from "../i18n";
import { friendlyApiError } from "../i18n/apiErrors";

export function Personnel() {
  const { t } = useTranslation();
  const { canManagePersonnel } = useAuth();
  const [search, setSearch] = useState("");
  // Conscripts (production_scope=false) are outside the personnel roster;
  // they stay reachable through the scope filter but are hidden by default.
  const [scope, setScope] = useState<string>("true");
  const [activeFilter, setActiveFilter] = useState<string>("");
  const [scanStatus, setScanStatus] = useState<ScanStatus | "">("");
  const [branch, setBranch] = useState("");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [showAddModal, setShowAddModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const limit = 25;

  const { data, loading, error, reload } = useApi(
    (s) =>
      api.humans(
        {
          limit,
          offset: page * limit,
          search: search || undefined,
          production_scope: scope === "true" ? true : scope === "false" ? false : undefined,
          active: activeFilter === "true" ? true : activeFilter === "false" ? false : undefined,
          scan_status: scanStatus || undefined,
          branch: branch || undefined,
        },
        s
      ),
    [search, scope, activeFilter, scanStatus, branch, page]
  );
  const summary = useApi((s) => api.humansSummary(s), []);
  const branches = useApi((s) => api.humanBranches(s), []);

  function refreshAll() {
    reload();
    summary.reload();
  }

  function toggleSelected(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const pageIds = (data?.items ?? []).filter((h) => h.active).map((h) => h.employee_id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => selected.has(id));

  function applyScanFilter(next: ScanStatus | "") {
    setScanStatus(next);
    // scan_status already implies active/inactive; avoid contradictory combos.
    setActiveFilter("");
    setPage(0);
  }

  async function handleExport() {
    setExportBusy(true);
    setExportError(null);
    try {
      const active = activeFilter === "true" ? true : activeFilter === "false" ? false : undefined;
      const blob = await api.exportHumansCsv(active);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "personnel_export.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(friendlyApiError(err, t));
    } finally {
      setExportBusy(false);
    }
  }

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
          <button
            onClick={handleExport}
            disabled={exportBusy}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 disabled:opacity-50"
          >
            {t.personnel.exportCsvButton}
          </button>
          {canManagePersonnel && (
            <>
              <button
                onClick={() => setShowImportModal(true)}
                className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50"
              >
                {t.personnel.importCsvButton}
              </button>
              <button
                onClick={() => setShowAddModal(true)}
                className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-blue-700"
              >
                {t.personnel.addPersonnelButton}
              </button>
            </>
          )}
        </div>
      </div>

      <PersonnelHub
        summary={summary.data}
        canManage={canManagePersonnel}
        activeScanFilter={scanStatus}
        onFilter={applyScanFilter}
        onImport={() => setShowImportModal(true)}
        onAdd={() => setShowAddModal(true)}
      />

      <ReadinessCard
        onPickBranch={(b) => {
          setScanStatus("needs_enrollment");
          setActiveFilter("");
          setBranch(b === "—" ? "" : b);
          setPage(0);
        }}
      />

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
        <div>
          <select
            value={activeFilter}
            onChange={(e) => {
              setActiveFilter(e.target.value);
              setPage(0);
            }}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
            <option value="">{t.personnel.filterAll}</option>
            <option value="true">{t.personnel.filterActiveOnly}</option>
            <option value="false">{t.personnel.filterInactiveOnly}</option>
          </select>
        </div>
        <div>
          <select
            value={scanStatus}
            onChange={(e) => applyScanFilter(e.target.value as ScanStatus | "")}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
            <option value="">{t.workflow.filterScanAll}</option>
            <option value="needs_enrollment">{t.workflow.scanNeeds}</option>
            <option value="enrolled">{t.workflow.scanEnrolled}</option>
            <option value="exempt">{t.workflow.scanExempt}</option>
            <option value="left_with_account">{t.workflow.scanLeftWithAccount}</option>
          </select>
        </div>
        <div>
          <select
            value={branch}
            onChange={(e) => {
              setBranch(e.target.value);
              setPage(0);
            }}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
          >
            <option value="">{t.workflow.allBranches}</option>
            {branches.data?.map((b) => (
              <option key={b} value={b}>
                {b}
              </option>
            ))}
          </select>
        </div>
      </div>

      {canManagePersonnel && selected.size > 0 && (
        <BulkExemptBar
          ids={[...selected]}
          onDone={() => {
            setSelected(new Set());
            refreshAll();
          }}
          onClear={() => setSelected(new Set())}
        />
      )}

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
                  {canManagePersonnel && (
                    <th className="w-8">
                      <input
                        type="checkbox"
                        title={t.workflow.selectPage}
                        checked={allPageSelected}
                        onChange={() =>
                          setSelected((prev) => {
                            const next = new Set(prev);
                            if (allPageSelected) pageIds.forEach((id) => next.delete(id));
                            else pageIds.forEach((id) => next.add(id));
                            return next;
                          })
                        }
                      />
                    </th>
                  )}
                  <th>{t.personnel.thaiName}</th>
                  <th>{t.personnel.englishName}</th>
                  <th>{t.personnel.rank}</th>
                  <th>{t.workflow.positionCol}</th>
                  <th>{t.personnel.branch}</th>
                  <th>{t.personnel.scope}</th>
                  <th>{t.workflow.colScan}</th>
                  <th>{t.common.status}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data?.items.map((h) => (
                  <tr key={h.employee_id} className="transition-colors hover:bg-slate-50/80">
                    {canManagePersonnel && (
                      <td>
                        <input
                          type="checkbox"
                          disabled={!h.active}
                          checked={selected.has(h.employee_id)}
                          onChange={() => toggleSelected(h.employee_id)}
                        />
                      </td>
                    )}
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
                    <td className="text-slate-600">{h.position ?? "—"}</td>
                    <td className="text-slate-600">{h.branch ?? "—"}</td>
                    <td>
                      <ScopeBadge scope={h.production_scope} />
                    </td>
                    <td>
                      {canManagePersonnel && h.active ? (
                        <div className="flex items-center gap-1.5">
                          <QuickScanPolicy human={h} onChanged={refreshAll} />
                          {h.has_active_terminal_account && (
                            <span className="text-[11px] font-semibold text-emerald-700">✓ {t.workflow.scanEnrolled}</span>
                          )}
                        </div>
                      ) : (
                        <ScanStateBadge human={h} />
                      )}
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

      {exportError && <ErrorBanner message={exportError} />}

      {showAddModal && (
        <PersonnelFormModal
          mode="create"
          onClose={() => setShowAddModal(false)}
          // Do NOT close on save — PersonnelFormModal shows its own
          // "เพิ่มกำลังพลเรียบร้อยแล้ว" + Enrollment-handoff screen first;
          // it closes itself. Just refresh the list underneath.
          onSaved={() => {
            reload();
            summary.reload();
          }}
        />
      )}
      {showImportModal && (
        <CsvImportModal
          onClose={() => setShowImportModal(false)}
          onCommitted={() => {
            reload();
            summary.reload();
          }}
        />
      )}
    </div>
  );
}

export function HumanDetail() {
  const { employeeId } = useParams<{ employeeId: string }>();
  const { me, canEditRoster, canManagePersonnel } = useAuth();
  const { t } = useTranslation();
  const { data, loading, error, reload } = useApi((s) => api.human(employeeId as string, s), [employeeId]);

  const [showEditModal, setShowEditModal] = useState(false);
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
        setSaveError(friendlyApiError(err, t));
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
        <div className="flex items-center gap-2">
          {canManagePersonnel && (
            <button
              onClick={() => setShowEditModal(true)}
              className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50"
            >
              {t.personnel.editPersonnelButton}
            </button>
          )}
          <ScopeBadge scope={data.production_scope} />
        </div>
      </div>

      {showEditModal && (
        <PersonnelFormModal
          mode="edit"
          human={data}
          onClose={() => setShowEditModal(false)}
          onSaved={() => reload()}
        />
      )}

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
                      disabled={!canEditRoster}
                      title={!canEditRoster ? t.personnel.writesDisabledNotice : t.personnel.editEnglishName}
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
            hint={t.personnel.rankSourceManagedHint}
          />
          <Row label={t.personnel.position} value={data.position ?? "—"} />
          <Row label={t.personnel.branch} value={data.branch ?? "—"} />
          <Row label={t.personnel.category} value={data.category ?? "—"} />
          <Row
            label={t.personnel.scope}
            value={data.production_scope ? t.personnel.productionScope : t.personnel.excludedScope}
          />
          <Row
            label={t.personnel.statusLabel}
            value={data.active ? t.personnel.statusActive : t.personnel.statusInactive}
          />
          <Row label="UUID" value={data.employee_id} mono />
        </dl>
      </div>

      {/* ADMS-UX-CrossLifecycleClosure-021B: an ACTIVE Human with no
          current working terminal account (e.g. the account was removed
          as part of a cleanup) must read as "needs re-enrollment," never
          as "inactive" — removing a terminal account is not the same fact
          as a person leaving. has_active_terminal_account is server-
          derived (app/api/repository.py) from the same underlying facts
          Terminal Management and Enrollment use, so this page can never
          disagree with them about whether the account currently works. */}
      {data.active && !data.scan_exempt && data.has_active_terminal_account === false && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
          <div className="text-sm font-bold text-amber-900">{t.personnel.noTerminalAccountTitle}</div>
          <p className="mt-1 text-xs text-amber-800">{t.personnel.noTerminalAccountBody}</p>
          <div className="mt-3">
            <EnrollLink human={data} />
          </div>
        </div>
      )}

      <ScanPolicyCard human={data} onChanged={reload} />

      <TerminalNameCard human={data} />

      <PersonAbsences employeeId={data.employee_id} active={data.active} />

      {/* ADMS-Personnel-Lifecycle-019: one obvious primary lifecycle action,
          no internal identifiers exposed. */}
      {isAdmin && <OffboardPanel human={data} onChanged={reload} />}

      <div>
        <Link to="/personnel" className="text-xs font-semibold text-blue-600 hover:underline">
          ← {t.common.back} {t.personnel.title}
        </Link>
      </div>
    </div>
  );
}

function Row({ label, value, mono, hint }: { label: string; value: string; mono?: boolean; hint?: string }) {
  return (
    <div className="flex items-center px-4 py-2.5">
      <dt className="w-44 shrink-0 font-bold uppercase text-[10px] text-slate-400">{label}</dt>
      <dd className={`text-slate-900 ${mono ? "font-mono text-[11px]" : ""}`}>
        {value}
        {hint && <span className="ml-2 text-[10px] font-normal text-slate-400">({hint})</span>}
      </dd>
    </div>
  );
}

type ScanStatus = "needs_enrollment" | "enrolled" | "exempt" | "left_with_account";

type PersonnelSummaryData = {
  active: number;
  inactive: number;
  scan_exempt: number;
  needs_enrollment: number;
  left_with_terminal_account: number;
};

/** Separates the roster jobs (Excel update, new arrival, leaving, scan-exempt)
 * so each has its own obvious entry point, and turns the counts that need
 * attention into one-click filters. */
function PersonnelHub({
  summary,
  canManage,
  activeScanFilter,
  onFilter,
  onImport,
  onAdd,
}: {
  summary: PersonnelSummaryData | null | undefined;
  canManage: boolean;
  activeScanFilter: ScanStatus | "";
  onFilter: (s: ScanStatus | "") => void;
  onImport: () => void;
  onAdd: () => void;
}) {
  const { t } = useTranslation();
  const counts: { key: ScanStatus | ""; label: string; value?: number; tone: string }[] = [
    { key: "", label: t.workflow.countActive, value: summary?.active, tone: "text-slate-900" },
    { key: "needs_enrollment", label: t.workflow.countNeedsEnroll, value: summary?.needs_enrollment, tone: "text-amber-700" },
    { key: "exempt", label: t.workflow.countExempt, value: summary?.scan_exempt, tone: "text-purple-700" },
    {
      key: "left_with_account",
      label: t.workflow.countLeftWithAccount,
      value: summary?.left_with_terminal_account,
      tone: "text-rose-700",
    },
  ];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {counts.map((c) => (
          <button
            key={c.key || "all"}
            type="button"
            onClick={() => onFilter(c.key)}
            className={`rounded-lg border bg-white p-3 text-left shadow-2xs transition-colors hover:bg-slate-50 ${
              activeScanFilter === c.key ? "border-blue-500 ring-1 ring-blue-500" : "border-slate-200"
            }`}
          >
            <div className="text-[11px] font-semibold text-slate-500">{c.label}</div>
            <div className={`mt-1 text-2xl font-bold ${c.tone}`}>{c.value ?? "—"}</div>
          </button>
        ))}
      </div>
      <div>
        <h2 className="mb-2 text-xs font-bold uppercase tracking-wider text-slate-500">{t.workflow.hubTitle}</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          <TaskCard
            title={t.workflow.importTitle}
            desc={t.workflow.importDesc}
            action={canManage ? { label: t.personnel.importCsvButton, onClick: onImport } : undefined}
          />
          <TaskCard
            title={t.workflow.joinTitle}
            desc={t.workflow.joinDesc}
            action={canManage ? { label: t.personnel.addPersonnelButton, onClick: onAdd } : undefined}
          />
          <TaskCard
            title={t.workflow.leaveTitle}
            desc={t.workflow.leaveDesc}
            action={{ label: t.workflow.countLeftWithAccount, onClick: () => onFilter("left_with_account") }}
          />
          <TaskCard
            title={t.workflow.exemptTitle}
            desc={t.workflow.exemptDesc}
            action={{ label: t.workflow.countExempt, onClick: () => onFilter("exempt") }}
          />
        </div>
      </div>
    </div>
  );
}

function TaskCard({
  title,
  desc,
  action,
}: {
  title: string;
  desc: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <div className="flex flex-col justify-between rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
      <div>
        <div className="text-sm font-bold text-slate-900">{title}</div>
        <p className="mt-1 text-xs leading-relaxed text-slate-600">{desc}</p>
      </div>
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="mt-3 self-start rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50"
        >
          {action.label}
        </button>
      )}
    </div>
  );
}

function ScanStateBadge({ human }: { human: Human }) {
  const { t } = useTranslation();
  if (!human.active) {
    return human.has_active_terminal_account ? (
      <span className="font-semibold text-rose-700">{t.workflow.scanLeftWithAccount}</span>
    ) : (
      <span className="text-slate-400">—</span>
    );
  }
  if (human.scan_exempt) {
    return (
      <span className="font-semibold text-purple-700" title={human.scan_exempt_reason ?? undefined}>
        {t.workflow.scanExempt}
      </span>
    );
  }
  return human.has_active_terminal_account ? (
    <span className="font-semibold text-emerald-700">✓ {t.workflow.scanEnrolled}</span>
  ) : (
    <span className="font-semibold text-amber-700">{t.workflow.scanNeeds}</span>
  );
}

function PersonAbsences({ employeeId, active }: { employeeId: string; active: boolean }) {
  const { t } = useTranslation();
  const { canRecordAbsence } = useAuth();
  const list = useApi((s) => api.absences({ employee_id: employeeId, limit: 50 }, s), [employeeId]);
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-slate-900">{t.leave.historyTitle}</h2>
        {canRecordAbsence && active && (
          <Link
            to={`/absences?employee=${employeeId}`}
            className="rounded-md border border-slate-300 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            + {t.leave.addForPerson}
          </Link>
        )}
      </div>
      {list.error ? <ErrorBanner message={list.error} /> : <AbsenceTable items={list.data?.items ?? []} onChanged={list.reload} />}
    </div>
  );
}

/** Per-row scan policy: must scan, or exempt as finance / commander's office.
 * Applies immediately (same bulk endpoint, one id). */
function QuickScanPolicy({ human, onChanged }: { human: Human; onChanged: () => void }) {
  const { t } = useTranslation();
  const { canEditRoster } = useAuth();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const current = human.scan_exempt ? human.scan_exempt_reason ?? "" : "";
  const presets = EXEMPT_REASON_PRESETS as readonly string[];

  async function change(value: string) {
    setBusy(true);
    setError(null);
    try {
      await api.bulkScanExempt([human.employee_id], value !== "", value || null);
      onChanged();
    } catch (err) {
      setError(friendlyApiError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <select
        value={current}
        disabled={!canEditRoster || busy}
        title={!canEditRoster ? t.workflow.needsWriteWindow : undefined}
        onChange={(e) => change(e.target.value)}
        className={`rounded border px-1.5 py-0.5 text-[11px] font-semibold disabled:opacity-60 ${
          human.scan_exempt ? "border-purple-300 bg-purple-50 text-purple-800" : "border-amber-300 bg-amber-50 text-amber-800"
        }`}
      >
        <option value="">{t.workflow.quickRequired}</option>
        {presets.map((r) => (
          <option key={r} value={r}>
            {t.workflow.quickExemptPrefix} {r}
          </option>
        ))}
        {current && !presets.includes(current) && (
          <option value={current}>
            {t.workflow.quickExemptPrefix} {current}
          </option>
        )}
      </select>
      {error && <div className="text-[10px] text-rose-700">{error}</div>}
    </div>
  );
}

function BulkExemptBar({ ids, onDone, onClear }: { ids: string[]; onDone: () => void; onClear: () => void }) {
  const { t } = useTranslation();
  const { canEditRoster } = useAuth();
  const [preset, setPreset] = useState<string>(EXEMPT_REASON_PRESETS[0]);
  const [other, setOther] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const reason = preset === "__other" ? other.trim() : preset;

  async function apply(exempt: boolean) {
    setBusy(true);
    setMsg(null);
    try {
      const res = await api.bulkScanExempt(ids, exempt, exempt ? reason || null : null);
      setMsg({ ok: true, text: t.workflow.bulkDone.replace("{n}", String(res.changed)) });
      onDone();
    } catch (err) {
      setMsg({ ok: false, text: friendlyApiError(err, t) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-purple-200 bg-purple-50 px-3 py-2 text-xs">
      <span className="font-bold text-purple-900">{t.workflow.selectedCount.replace("{n}", String(ids.length))}</span>
      <select
        value={preset}
        onChange={(e) => setPreset(e.target.value)}
        className="rounded border border-purple-300 bg-white px-2 py-1"
      >
        {EXEMPT_REASON_PRESETS.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
        <option value="__other">{t.workflow.reasonOther}</option>
      </select>
      {preset === "__other" && (
        <input
          value={other}
          onChange={(e) => setOther(e.target.value)}
          placeholder={t.workflow.exemptReasonPlaceholder}
          className="rounded border border-purple-300 bg-white px-2 py-1"
        />
      )}
      <button
        type="button"
        onClick={() => apply(true)}
        disabled={!canEditRoster || busy || !reason}
        className="rounded bg-purple-700 px-3 py-1 font-bold text-white hover:bg-purple-800 disabled:opacity-40"
      >
        {t.workflow.bulkExempt}
      </button>
      <button
        type="button"
        onClick={() => apply(false)}
        disabled={!canEditRoster || busy}
        className="rounded border border-slate-300 bg-white px-3 py-1 font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
      >
        {t.workflow.bulkRequire}
      </button>
      <button type="button" onClick={onClear} className="ml-auto text-[11px] font-semibold text-slate-600 hover:underline">
        {t.workflow.clearSelection}
      </button>
      {!canEditRoster && <span className="w-full text-[11px] text-amber-800">{t.workflow.needsWriteWindow}</span>}
      {msg && <span className={`w-full font-semibold ${msg.ok ? "text-emerald-700" : "text-rose-700"}`}>{msg.text}</span>}
    </div>
  );
}

/** How far each section is with fingerprint enrollment. Click a section to
 * list who is still missing. */
function ReadinessCard({ onPickBranch }: { onPickBranch: (branch: string) => void }) {
  const { t } = useTranslation();
  const r = useApi((s) => api.readiness(s), []);
  if (!r.data) return null;
  const rows = r.data.branches;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-bold text-slate-900">
          {t.leave.readinessTitle}{" "}
          <span className={r.data.total.percent === 100 ? "text-emerald-700" : "text-amber-700"}>
            {r.data.total.percent}%
          </span>
        </h2>
        <p className="text-[11px] text-slate-500">{t.leave.readinessHint}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left text-xs table-dense">
          <thead>
            <tr>
              <th>{t.leave.branch}</th>
              <th className="text-center">{t.leave.readinessRequired}</th>
              <th className="text-center">{t.leave.readinessEnrolled}</th>
              <th className="text-center">{t.leave.readinessMissing}</th>
              <th className="text-center">{t.leave.readinessAway}</th>
              <th className="text-center">{t.workflow.scanExempt}</th>
              <th className="w-1/3" />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((b) => (
              <tr
                key={b.branch}
                onClick={() => b.missing > 0 && onPickBranch(b.branch)}
                className={b.missing > 0 ? "cursor-pointer hover:bg-amber-50/60" : ""}
              >
                <td className="font-semibold text-slate-800">{b.branch}</td>
                <td className="text-center">{b.required}</td>
                <td className="text-center text-emerald-700">{b.enrolled}</td>
                <td className={`text-center ${b.missing ? "font-bold text-amber-700" : "text-slate-300"}`}>{b.missing}</td>
                <td className="text-center text-sky-700">{b.away || ""}</td>
                <td className="text-center text-purple-700">{b.exempt || ""}</td>
                <td>
                  <div className="h-2 rounded bg-slate-100">
                    <div
                      className={`h-2 rounded ${b.percent === 100 ? "bg-emerald-500" : "bg-amber-400"}`}
                      style={{ width: `${b.percent}%` }}
                    />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
