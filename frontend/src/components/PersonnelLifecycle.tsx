import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiClientError } from "../api/client";
import type { Human } from "../api/types";
import { useAuth } from "../auth";
import { useApi } from "../hooks/useApi";
import { useTranslation } from "../i18n";
import { friendlyApiError } from "../i18n/apiErrors";
import { ConfirmModal } from "./ConfirmModal";

// The two places whose staff may be exempt from scanning. Stored verbatim as
// scan_exempt_reason (data, not UI copy), so they stay Thai in every locale.
export const EXEMPT_REASON_PRESETS = ["การเงิน", "สำนักงานผู้บังคับบัญชา"] as const;

function writeError(err: unknown, t: ReturnType<typeof useTranslation>["t"]): string {
  if (
    err instanceof ApiClientError &&
    (err.code === "WRITE_DISABLED" || err.code === "WRITE_SESSION_REQUIRED" || err.code === "WRITE_SESSION_EXPIRED")
  ) {
    return t.personnel.writesDisabledNotice;
  }
  return friendlyApiError(err, t);
}

/** Whether this person must scan in/out. Exempt people (commander's office,
 * finance) are left out of "needs enrollment" lists and absence counts. */
export function ScanPolicyCard({ human, onChanged }: { human: Human; onChanged: () => void }) {
  const { t } = useTranslation();
  const { canManagePersonnel, canEditRoster } = useAuth();
  const [reason, setReason] = useState(human.scan_exempt_reason ?? "");
  const [reasonError, setReasonError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  async function save(exempt: boolean) {
    if (exempt && !reason.trim()) {
      setReasonError(true);
      return;
    }
    setBusy(true);
    setMsg(null);
    try {
      await api.setScanExempt(human.employee_id, exempt, exempt ? reason.trim() : null);
      setMsg({ ok: true, text: t.workflow.savedOk });
      onChanged();
    } catch (err) {
      setMsg({ ok: false, text: writeError(err, t) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
      <div className="flex items-center justify-between">
        <div className="text-sm font-bold text-slate-900">{t.workflow.scanPolicyTitle}</div>
        <span
          className={`rounded px-2 py-0.5 text-[11px] font-bold ${
            human.scan_exempt ? "bg-purple-100 text-purple-800" : "bg-slate-100 text-slate-700"
          }`}
        >
          {human.scan_exempt ? t.workflow.scanExemptLabel : t.workflow.scanRequired}
        </span>
      </div>
      {human.scan_exempt && human.scan_exempt_reason && (
        <p className="mt-1 text-xs text-slate-600">
          {t.workflow.exemptReasonLabel}: {human.scan_exempt_reason}
        </p>
      )}

      {canManagePersonnel && human.active && (
        <div className="mt-3 space-y-2">
          {!human.scan_exempt && (
            <div>
              <label className="block text-[11px] font-bold text-slate-700">{t.workflow.exemptReasonLabel}</label>
              <div className="mt-1 flex flex-wrap gap-1.5">
                {EXEMPT_REASON_PRESETS.map((r) => (
                  <button
                    key={r}
                    type="button"
                    onClick={() => {
                      setReason(r);
                      setReasonError(false);
                    }}
                    className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${
                      reason === r ? "border-purple-500 bg-purple-50 text-purple-800" : "border-slate-300 bg-white text-slate-600"
                    }`}
                  >
                    {r}
                  </button>
                ))}
              </div>
              <input
                type="text"
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value);
                  setReasonError(false);
                }}
                placeholder={t.workflow.exemptReasonPlaceholder}
                className={`mt-1 w-full rounded-md border bg-white px-2.5 py-1.5 text-xs ${
                  reasonError ? "border-rose-500 ring-1 ring-rose-300" : "border-slate-300"
                }`}
              />
              {reasonError && (
                <div className="mt-1 text-[11px] font-semibold text-rose-700">{t.workflow.exemptReasonRequired}</div>
              )}
            </div>
          )}
          <button
            type="button"
            disabled={!canEditRoster || busy}
            onClick={() => save(!human.scan_exempt)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? t.common.saving : human.scan_exempt ? t.workflow.clearExemptButton : t.workflow.setExemptButton}
          </button>
          {!canEditRoster && <p className="text-[11px] text-amber-800">{t.workflow.needsWriteWindow}</p>}
        </div>
      )}
      {msg && (
        <div className={`mt-2 text-xs font-semibold ${msg.ok ? "text-emerald-700" : "text-rose-700"}`}>{msg.text}</div>
      )}
    </div>
  );
}

/** One action for someone leaving the unit: close them in the roster
 * (attendance history and mappings are preserved/closed by the server),
 * then remove their account and fingerprints from every scanner. If the
 * scanner step fails, the person stays closed and a retry is offered. */
export function OffboardPanel({ human, onChanged }: { human: Human; onChanged: () => void }) {
  const { t } = useTranslation();
  const { me, canEditRoster, canMutate } = useAuth();
  const accounts = useApi((s) => api.humanTerminalAccounts(human.employee_id, s), [human.employee_id, human.active]);
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);

  const accountList = accounts.data ?? [];
  const operator = me?.username ?? "";

  async function removeAccounts(): Promise<boolean> {
    let allOk = true;
    for (const a of accountList) {
      try {
        await api.removeTerminalAccount(a.device_id, a.device_user_id, operator, true);
      } catch {
        allOk = false;
      }
    }
    return allOk;
  }

  async function handleOffboard() {
    if (!reason.trim()) {
      setReasonError(true);
      return;
    }
    setBusy(true);
    setResult(null);
    try {
      await api.deactivateHuman(human.employee_id, reason.trim());
    } catch (err) {
      setBusy(false);
      setOpen(false);
      setResult({ ok: false, text: writeError(err, t) });
      return;
    }
    // Removing from the scanner is fingerprint work and needs the Work
    // Session; outside it the person is still closed and the removal waits
    // in "left, still on scanner".
    if (accountList.length > 0 && !canMutate) {
      setResult({ ok: false, text: t.workflow.offboardDeferred });
    } else {
      const removed = await removeAccounts();
      setResult({ ok: removed, text: removed ? t.workflow.offboardDone : t.workflow.offboardPartial });
    }
    setBusy(false);
    setOpen(false);
    setReason("");
    accounts.reload();
    onChanged();
  }

  async function handleRetryRemove() {
    setBusy(true);
    const removed = await removeAccounts();
    setResult({ ok: removed, text: removed ? t.workflow.offboardDone : t.workflow.offboardPartial });
    setBusy(false);
    accounts.reload();
    onChanged();
  }

  async function handleReactivate() {
    setBusy(true);
    setResult(null);
    try {
      await api.reactivateHuman(human.employee_id);
      setResult({ ok: true, text: t.personnel.reactivateSuccess });
      onChanged();
    } catch (err) {
      setResult({ ok: false, text: writeError(err, t) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs space-y-3">
      {result && (
        <div
          className={`rounded-md border p-3 text-xs font-semibold ${
            result.ok ? "border-emerald-200 bg-emerald-50 text-emerald-800" : "border-rose-200 bg-rose-50 text-rose-800"
          }`}
        >
          {result.text}
        </div>
      )}

      {human.active ? (
        <button
          type="button"
          onClick={() => {
            setReason("");
            setReasonError(false);
            setOpen(true);
          }}
          disabled={!canEditRoster || busy}
          className="w-full rounded-md bg-rose-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-rose-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {t.workflow.offboardButton}
        </button>
      ) : (
        <>
          {accountList.length > 0 && (
            <button
              type="button"
              onClick={handleRetryRemove}
              disabled={!canMutate || busy}
              className="w-full rounded-md bg-rose-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-rose-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {busy ? t.common.saving : `${t.workflow.retryRemoveButton} (${accountList.length})`}
            </button>
          )}
          {accountList.length > 0 && !canMutate && (
            <p className="text-[11px] text-amber-800">{t.workflow.fingerprintWindowNeeded}</p>
          )}
          <p className="text-[11px] text-slate-600">{t.workflow.rejoinHint}</p>
          <button
            type="button"
            onClick={handleReactivate}
            disabled={!canEditRoster || busy}
            className="w-full rounded-md bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {t.personnel.reactivateButton}
          </button>
        </>
      )}
      {!canEditRoster && <p className="text-[11px] text-amber-800">{t.workflow.needsWriteWindow}</p>}

      <ConfirmModal
        open={open}
        title={t.workflow.offboardTitle}
        tone="danger"
        confirmLabel={t.workflow.offboardButton}
        busy={busy}
        onConfirm={handleOffboard}
        onCancel={() => setOpen(false)}
      >
        <p className="text-xs leading-relaxed text-slate-600">{t.workflow.offboardBody}</p>
        <div className="rounded-md border border-slate-200 bg-slate-50 p-2 text-xs">
          <div className="font-bold text-slate-700">{t.workflow.offboardAccounts}</div>
          {accountList.length === 0 ? (
            <div className="text-slate-500">{t.workflow.offboardNoAccounts}</div>
          ) : (
            <ul className="mt-1 list-inside list-disc font-mono text-[11px] text-slate-700">
              {accountList.map((a) => (
                <li key={`${a.device_id}:${a.device_user_id}`}>
                  #{a.device_id} · {a.device_user_id}
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <label className="block text-[11px] font-bold text-slate-700">{t.personnel.deactivateReasonLabel}</label>
          <input
            type="text"
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              setReasonError(false);
            }}
            placeholder={t.workflow.offboardReasonPlaceholder}
            className={`mt-1 w-full rounded-md border bg-white px-2.5 py-1.5 text-xs text-slate-900 ${
              reasonError ? "border-rose-500 ring-1 ring-rose-300" : "border-slate-300"
            }`}
          />
          {reasonError && (
            <div className="mt-1 text-[11px] font-semibold text-rose-700">{t.personnel.deactivateReasonRequired}</div>
          )}
        </div>
      </ConfirmModal>
    </div>
  );
}

export function EnrollLink({ human }: { human: Human }) {
  const { t } = useTranslation();
  const { canEnroll } = useAuth();
  if (!canEnroll || !human.active || human.scan_exempt || human.has_active_terminal_account) return null;
  return (
    <Link
      to={`/enrollments?employee=${human.employee_id}`}
      className="inline-flex items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700"
    >
      {t.workflow.enrollButton}
    </Link>
  );
}
