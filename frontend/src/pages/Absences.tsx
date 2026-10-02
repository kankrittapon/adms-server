import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { ConfirmModal } from "../components/ConfirmModal";
import { PersonCombobox } from "../components/PersonCombobox";
import { ErrorBanner, Loading } from "../components/Status";
import { useApi } from "../hooks/useApi";
import { useTranslation } from "../i18n";
import { friendlyApiError } from "../i18n/apiErrors";

export function todayLocal(): string {
  // en-CA formats as YYYY-MM-DD; pin the unit's timezone.
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Bangkok" });
}

export function formatThaiDate(d: string): string {
  return new Date(`${d}T00:00:00`).toLocaleDateString("th-TH", { day: "numeric", month: "short", year: "2-digit" });
}

function absenceError(err: unknown, t: ReturnType<typeof useTranslation>["t"]): string {
  if (err instanceof ApiClientError) {
    if (err.code === "ABSENCE_OVERLAP") return t.leave.overlap;
    if (err.code === "WRITE_DISABLED" || err.code === "WRITE_SESSION_REQUIRED" || err.code === "WRITE_SESSION_EXPIRED") {
      return t.personnel.writesDisabledNotice;
    }
  }
  return friendlyApiError(err, t);
}

/** Record-only leave register: the commander has already signed the paper,
 * so this only records who is away, which days, and why. */
export function Absences() {
  const { t } = useTranslation();
  const { canRecordAbsence, isAdmin } = useAuth();
  const [searchParams] = useSearchParams();
  const [scope, setScope] = useState<"current" | "all">("current");
  const [showCancelled, setShowCancelled] = useState(false);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const limit = 50;

  const list = useApi(
    (s) =>
      api.absences(
        {
          limit,
          offset: page * limit,
          on_or_after: scope === "current" ? todayLocal() : undefined,
          include_cancelled: showCancelled,
          search: search || undefined,
        },
        s
      ),
    [scope, showCancelled, search, page]
  );

  return (
    <div className="space-y-5">
      <div className="border-b border-slate-200 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.leave.title}</h1>
        <p className="text-xs text-slate-500">{t.leave.subtitle}</p>
      </div>

      {canRecordAbsence && (
        <AbsenceForm initialEmployeeId={searchParams.get("employee") ?? ""} onSaved={() => list.reload()} />
      )}

      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">{t.leave.listTitle}</h2>
          <div className="inline-flex rounded-md border border-slate-300 bg-white p-0.5 text-xs">
            {(["current", "all"] as const).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => {
                  setScope(v);
                  setPage(0);
                }}
                className={`rounded px-2.5 py-1 font-semibold ${scope === v ? "bg-blue-600 text-white" : "text-slate-600"}`}
              >
                {v === "current" ? t.leave.filterCurrent : t.leave.filterAll}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1.5 text-xs text-slate-600">
            <input type="checkbox" checked={showCancelled} onChange={(e) => setShowCancelled(e.target.checked)} />
            {t.leave.showCancelled}
          </label>
          <input
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            placeholder={t.common.searchPlaceholder}
            className="min-w-[200px] flex-1 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs"
          />
        </div>

        {list.loading ? (
          <Loading />
        ) : list.error ? (
          <ErrorBanner message={list.error} />
        ) : (
          <AbsenceTable items={list.data?.items ?? []} onChanged={() => list.reload()} showPerson />
        )}

        {list.data && list.data.total > limit && (
          <div className="flex items-center justify-end gap-2 text-xs">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={page === 0}
              className="rounded border border-slate-300 bg-white px-2.5 py-1 disabled:opacity-40"
            >
              {t.common.back}
            </button>
            <span>
              {page + 1} / {Math.ceil(list.data.total / limit)}
            </span>
            <button
              onClick={() => setPage((p) => p + 1)}
              disabled={(page + 1) * limit >= list.data.total}
              className="rounded border border-slate-300 bg-white px-2.5 py-1 disabled:opacity-40"
            >
              {t.common.next}
            </button>
          </div>
        )}
      </div>

      {isAdmin && <HolidayManager />}
    </div>
  );
}

function AbsenceForm({ initialEmployeeId, onSaved }: { initialEmployeeId: string; onSaved: () => void }) {
  const { t, locale } = useTranslation();
  const { canEditRoster } = useAuth();
  const humans = useApi((s) => api.humans({ active: true, production_scope: true, limit: 200 }, s), []);
  const types = useApi((s) => api.absenceTypes(s), []);
  const [employeeId, setEmployeeId] = useState(initialEmployeeId);
  const [typeCode, setTypeCode] = useState("SICK");
  const [startDate, setStartDate] = useState(todayLocal());
  const [endDate, setEndDate] = useState(todayLocal());
  const [orderRef, setOrderRef] = useState("");
  const [destination, setDestination] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const selectedType = types.data?.find((x) => x.code === typeCode);
  const isDuty = selectedType?.counts_as === "DUTY";
  const days =
    startDate && endDate && endDate >= startDate
      ? Math.round((new Date(endDate).getTime() - new Date(startDate).getTime()) / 86400000) + 1
      : 0;

  async function submit() {
    if (!employeeId || !startDate || !endDate || endDate < startDate) {
      setMsg({ ok: false, text: t.leave.selectPersonRequired });
      return;
    }
    if (selectedType?.requires_order_ref && !orderRef.trim()) {
      setMsg({ ok: false, text: t.leave.orderRefRequired });
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await api.createAbsence({
        employee_id: employeeId,
        type_code: typeCode,
        start_date: startDate,
        end_date: endDate,
        order_ref: orderRef.trim() || null,
        destination: isDuty ? destination.trim() || null : null,
        note: note.trim() || null,
      });
      setMsg({ ok: true, text: t.leave.saved });
      setEmployeeId("");
      setOrderRef("");
      setDestination("");
      setNote("");
      onSaved();
    } catch (err) {
      setMsg({ ok: false, text: absenceError(err, t) });
    } finally {
      setBusy(false);
    }
  }

  const input = "mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs disabled:bg-slate-100";
  const disabled = !canEditRoster || busy;

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50/30 p-4 shadow-2xs space-y-3">
      <h2 className="text-sm font-bold text-slate-900">{t.leave.formTitle}</h2>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div>
          <label className="block text-[11px] font-bold text-slate-700">{t.leave.person}</label>
          <PersonCombobox humans={humans.data?.items} value={employeeId} onChange={setEmployeeId} disabled={disabled} />
        </div>
        <div>
          <label className="block text-[11px] font-bold text-slate-700">{t.leave.type}</label>
          <select value={typeCode} onChange={(e) => setTypeCode(e.target.value)} disabled={disabled} className={input}>
            {types.data?.map((x) => (
              <option key={x.code} value={x.code}>
                {locale === "th" ? x.name_th : x.name_en}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-[11px] font-bold text-slate-700">{t.leave.startDate}</label>
          <input
            type="date"
            value={startDate}
            onChange={(e) => {
              setStartDate(e.target.value);
              if (endDate < e.target.value) setEndDate(e.target.value);
            }}
            disabled={disabled}
            className={input}
          />
        </div>
        <div>
          <label className="block text-[11px] font-bold text-slate-700">
            {t.leave.endDate} {days > 0 && <span className="font-normal text-slate-500">({days} {t.leave.days})</span>}
          </label>
          <input
            type="date"
            value={endDate}
            min={startDate}
            onChange={(e) => setEndDate(e.target.value)}
            disabled={disabled}
            className={input}
          />
        </div>
        <div>
          <label className="block text-[11px] font-bold text-slate-700">
            {t.leave.orderRef}
            {selectedType?.requires_order_ref && <span className="text-rose-600"> *</span>}
          </label>
          <input value={orderRef} onChange={(e) => setOrderRef(e.target.value)} disabled={disabled} className={input} />
        </div>
        {isDuty && (
          <div>
            <label className="block text-[11px] font-bold text-slate-700">{t.leave.destination}</label>
            <input value={destination} onChange={(e) => setDestination(e.target.value)} disabled={disabled} className={input} />
          </div>
        )}
        <div className={isDuty ? "" : "xl:col-span-2"}>
          <label className="block text-[11px] font-bold text-slate-700">{t.leave.note}</label>
          <input value={note} onChange={(e) => setNote(e.target.value)} disabled={disabled} className={input} />
        </div>
        <div className="flex items-end">
          <button
            type="button"
            onClick={submit}
            disabled={disabled || !employeeId}
            className="w-full rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busy ? t.common.saving : t.leave.saveButton}
          </button>
        </div>
      </div>
      {!canEditRoster && <p className="text-[11px] text-amber-800">{t.workflow.needsWriteWindow}</p>}
      {msg && <div className={`text-xs font-semibold ${msg.ok ? "text-emerald-700" : "text-rose-700"}`}>{msg.text}</div>}
    </div>
  );
}

type AbsenceItem = NonNullable<Awaited<ReturnType<typeof api.absences>>>["items"][number];

export function AbsenceTable({
  items,
  onChanged,
  showPerson,
}: {
  items: AbsenceItem[];
  onChanged: () => void;
  showPerson?: boolean;
}) {
  const { t, locale } = useTranslation();
  const { canRecordAbsence, canEditRoster } = useAuth();
  const [cancelTarget, setCancelTarget] = useState<AbsenceItem | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function confirmCancel() {
    if (!cancelTarget || !reason.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.cancelAbsence(cancelTarget.absence_id, reason.trim());
      setCancelTarget(null);
      setReason("");
      onChanged();
    } catch (err) {
      setCancelTarget(null);
      setError(absenceError(err, t));
    } finally {
      setBusy(false);
    }
  }

  if (items.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-6 text-center text-xs text-slate-500">
        {t.leave.noRecords}
      </div>
    );
  }

  return (
    <>
      {error && <ErrorBanner message={error} />}
      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white shadow-2xs">
        <table className="w-full border-collapse text-left text-xs table-dense">
          <thead>
            <tr>
              {showPerson && <th>{t.leave.person}</th>}
              <th>{t.leave.type}</th>
              <th>{t.leave.startDate}</th>
              <th>{t.leave.endDate}</th>
              <th>{t.leave.orderRef}</th>
              <th>{t.leave.note}</th>
              <th>{t.leave.recordedBy}</th>
              <th />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {items.map((a) => (
              <tr key={a.absence_id} className={a.status === "CANCELLED" ? "opacity-50" : ""}>
                {showPerson && (
                  <td>
                    <Link to={`/personnel/${a.employee_id}`} className="font-bold text-blue-600 hover:underline">
                      {a.rank ? `${a.rank} ` : ""}
                      {a.employee_name}
                    </Link>
                    {a.branch && <span className="ml-1 text-[11px] text-slate-500">{a.branch}</span>}
                  </td>
                )}
                <td>
                  <span
                    className={`rounded px-1.5 py-0.5 text-[11px] font-bold ${
                      a.counts_as === "DUTY" ? "bg-sky-100 text-sky-800" : "bg-amber-100 text-amber-800"
                    }`}
                  >
                    {locale === "th" ? a.type_name_th : a.type_name_en}
                  </span>
                </td>
                <td>{formatThaiDate(a.start_date)}</td>
                <td>
                  {formatThaiDate(a.end_date)}{" "}
                  <span className="text-slate-500">
                    ({a.days} {t.leave.days})
                  </span>
                </td>
                <td className="font-mono text-[11px]">{a.order_ref ?? "—"}</td>
                <td className="text-slate-600">
                  {[a.destination, a.note].filter(Boolean).join(" · ") || "—"}
                  {a.status === "CANCELLED" && (
                    <div className="text-[11px] font-semibold text-rose-700">
                      {t.leave.cancelled}: {a.cancel_reason}
                    </div>
                  )}
                </td>
                <td className="text-slate-500">{a.recorded_by}</td>
                <td>
                  {canRecordAbsence && a.status === "RECORDED" && (
                    <button
                      type="button"
                      disabled={!canEditRoster}
                      onClick={() => {
                        setReason("");
                        setCancelTarget(a);
                      }}
                      className="text-[11px] font-semibold text-rose-600 hover:underline disabled:opacity-40"
                    >
                      {t.leave.cancelButton}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ConfirmModal
        open={cancelTarget !== null}
        title={t.leave.cancelTitle}
        tone="danger"
        confirmLabel={t.leave.cancelButton}
        busy={busy}
        onConfirm={confirmCancel}
        onCancel={() => setCancelTarget(null)}
      >
        {cancelTarget && (
          <p className="text-xs text-slate-700">
            {cancelTarget.employee_name} · {locale === "th" ? cancelTarget.type_name_th : cancelTarget.type_name_en} ·{" "}
            {formatThaiDate(cancelTarget.start_date)} – {formatThaiDate(cancelTarget.end_date)}
          </p>
        )}
        <label className="block text-[11px] font-bold text-slate-700">{t.leave.cancelReason}</label>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t.leave.cancelReasonPlaceholder}
          className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs"
        />
      </ConfirmModal>
    </>
  );
}

function HolidayManager() {
  const { t } = useTranslation();
  const { canEditRoster } = useAuth();
  const year = Number(todayLocal().slice(0, 4));
  const list = useApi((s) => api.holidays(year, s), [year]);
  const [day, setDay] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function add() {
    if (!day || !name.trim()) return;
    setError(null);
    try {
      await api.setHoliday(day, name.trim());
      setDay("");
      setName("");
      list.reload();
    } catch (err) {
      setError(absenceError(err, t));
    }
  }

  async function remove(d: string) {
    setError(null);
    try {
      await api.deleteHoliday(d);
      list.reload();
    } catch (err) {
      setError(absenceError(err, t));
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs space-y-3">
      <div>
        <h2 className="text-sm font-bold text-slate-900">
          {t.leave.holidaysTitle} {year + 543}
        </h2>
        <p className="text-[11px] text-slate-500">{t.leave.holidayHint}</p>
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <input type="date" value={day} onChange={(e) => setDay(e.target.value)} className="rounded-md border border-slate-300 px-2.5 py-1.5 text-xs" />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={t.leave.holidayName}
          className="min-w-[200px] flex-1 rounded-md border border-slate-300 px-2.5 py-1.5 text-xs"
        />
        <button
          type="button"
          onClick={add}
          disabled={!canEditRoster || !day || !name.trim()}
          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-40"
        >
          {t.leave.holidayAdd}
        </button>
      </div>
      {error && <div className="text-xs font-semibold text-rose-700">{error}</div>}
      <ul className="divide-y divide-slate-100 text-xs">
        {list.data?.map((h) => (
          <li key={h.holiday_date} className="flex items-center justify-between py-1.5">
            <span>
              <span className="font-semibold">{formatThaiDate(h.holiday_date)}</span> — {h.name_th}
            </span>
            <button
              type="button"
              onClick={() => remove(h.holiday_date)}
              disabled={!canEditRoster}
              className="text-[11px] font-semibold text-rose-600 hover:underline disabled:opacity-40"
            >
              {t.common.delete}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
