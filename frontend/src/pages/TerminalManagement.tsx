import { useEffect, useRef, useState } from "react";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { ConfirmModal } from "../components/ConfirmModal";
import { ErrorBanner, Loading } from "../components/Status";
import { WriteSessionBadge } from "../components/WriteSessionControl";
import { useApi } from "../hooks/useApi";
import { useTranslation } from "../i18n";
import type { TerminalInventoryItem } from "../api/types";

const DEVICE_ID = 1; // this production system's only device

export function TerminalManagement() {
  const { me, canMutate } = useAuth();
  const { t } = useTranslation();
  const isAdmin = me?.role === "ADMIN";
  const inv = useApi((s) => api.terminalInventory(s), []);

  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [busyItem, setBusyItem] = useState<string | null>(null);

  const [fpConfirmItem, setFpConfirmItem] = useState<TerminalInventoryItem | null>(null);
  const [acctConfirmItem, setAcctConfirmItem] = useState<TerminalInventoryItem | null>(null);
  const [acctAcknowledge, setAcctAcknowledge] = useState(false);
  const [reenrollItem, setReenrollItem] = useState<TerminalInventoryItem | null>(null);
  const [reenrollStatus, setReenrollStatus] = useState<"idle" | "pending" | "confirmed" | "failed">("idle");
  const pollRef = useRef<number | null>(null);

  useEffect(() => () => {
    if (pollRef.current) window.clearInterval(pollRef.current);
  }, []);

  function friendlyError(err: unknown): string {
    if (err instanceof ApiClientError) {
      // Never surface raw Python/pyzk internals — the backend already
      // guarantees hand-written messages, but keep the mapping explicit
      // for the codes an elderly operator would otherwise see raw.
      if (err.code === "DEVICE_UNAVAILABLE") return t.terminalManagement.deviceUnreachable;
      if (err.code === "ACTIVE_HUMAN_PROTECTION") return t.terminalManagement.removeAccountActiveWarning;
      if (err.code === "WRITE_SESSION_REQUIRED" || err.code === "WRITE_DISABLED") {
        return t.enrollment.writeSessionLockedBody;
      }
      if (err.code === "WRITE_SESSION_EXPIRED") return t.enrollment.writeSessionExpiredMidWorkflow;
      return `${err.code}: ${err.message}`;
    }
    return err instanceof Error ? err.message : String(err);
  }

  async function handleRemoveFingerprint() {
    if (!fpConfirmItem) return;
    setBusyItem(fpConfirmItem.device_user_id);
    setActionError(null);
    try {
      const result = await api.removeTerminalFingerprint(
        DEVICE_ID, fpConfirmItem.device_user_id, me?.username ?? "operator"
      );
      setActionSuccess(
        result.already_absent ? t.terminalManagement.alreadyAbsentNotice : t.terminalManagement.fingerprintRemoveSuccess
      );
      setFpConfirmItem(null);
      inv.reload();
    } catch (err) {
      setActionError(friendlyError(err));
      setFpConfirmItem(null);
    } finally {
      setBusyItem(null);
    }
  }

  async function handleRemoveAccount() {
    if (!acctConfirmItem) return;
    setBusyItem(acctConfirmItem.device_user_id);
    setActionError(null);
    try {
      const result = await api.removeTerminalAccount(
        DEVICE_ID, acctConfirmItem.device_user_id, me?.username ?? "operator", acctAcknowledge
      );
      setActionSuccess(
        result.already_absent ? t.terminalManagement.alreadyAbsentNotice : t.terminalManagement.accountRemoveSuccess
      );
      setAcctConfirmItem(null);
      setAcctAcknowledge(false);
      inv.reload();
    } catch (err) {
      setActionError(friendlyError(err));
      // Keep the modal open on ACTIVE_HUMAN_PROTECTION so the operator can
      // see the warning and tick the acknowledgement, rather than losing
      // context — only close on other kinds of failure.
      if (!(err instanceof ApiClientError && err.code === "ACTIVE_HUMAN_PROTECTION")) {
        setAcctConfirmItem(null);
      }
    } finally {
      setBusyItem(null);
    }
  }

  async function handleStartReenroll() {
    if (!reenrollItem) return;
    const deviceUserId = reenrollItem.device_user_id;
    setBusyItem(deviceUserId);
    setActionError(null);
    setReenrollStatus("pending");
    try {
      await api.startFingerprintReenroll(deviceUserId, me?.username ?? "operator");
      // Poll the same Collector-health-bridge status every other
      // telemetry field already uses — no new transport, no blocking
      // browser request held open for up to ~180s.
      pollRef.current = window.setInterval(async () => {
        try {
          const status = await api.fingerprintReenrollStatus(deviceUserId);
          if (status.state === "confirmed" || status.state === "failed") {
            if (pollRef.current) window.clearInterval(pollRef.current);
            setReenrollStatus(status.state);
            setBusyItem(null);
            setActionSuccess(status.state === "confirmed" ? t.terminalManagement.reenrollSuccess : null);
            if (status.state === "failed") setActionError(t.terminalManagement.reenrollFailed);
            inv.reload();
          }
        } catch {
          // transient poll failure — keep polling, do not surface as an error
        }
      }, 3000);
    } catch (err) {
      setActionError(friendlyError(err));
      setReenrollStatus("idle");
      setBusyItem(null);
      setReenrollItem(null);
    }
  }

  if (!isAdmin) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.terminalManagement.title}</h1>
        <ErrorBanner message={t.terminalManagement.viewerNoAccess} />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.terminalManagement.title}</h1>
          <p className="text-xs text-slate-500">{t.terminalManagement.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <WriteSessionBadge />
          <button
            onClick={() => inv.reload()}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-2xs hover:bg-slate-50"
          >
            {t.terminalManagement.refreshButton}
          </button>
        </div>
      </div>

      {actionSuccess && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-medium text-emerald-800 shadow-2xs">
          {actionSuccess}
        </div>
      )}
      {actionError && <ErrorBanner message={actionError} />}

      {inv.loading ? (
        <Loading />
      ) : inv.error ? (
        <ErrorBanner message={inv.error} />
      ) : !inv.data?.device_reachable ? (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 text-xs text-amber-900">
          {t.terminalManagement.deviceUnreachable}
        </div>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xs">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs table-dense">
              <thead>
                <tr>
                  <th>{t.terminalManagement.nameColumn}</th>
                  <th>{t.terminalManagement.terminalIdColumn}</th>
                  <th>{t.terminalManagement.humanStatusColumn}</th>
                  <th>{t.terminalManagement.fingerprintStatusColumn}</th>
                  <th>{t.terminalManagement.mappingStatusColumn}</th>
                  <th></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {(inv.data?.items ?? []).map((item) => (
                  <tr key={item.device_user_id} className="hover:bg-slate-50/80">
                    <td className="font-bold text-slate-900">
                      {item.human_name ?? t.terminalManagement.humanUnlinked}
                    </td>
                    <td className="font-mono text-slate-700">{item.device_user_id}</td>
                    <td>
                      {item.human_active === true ? (
                        <span className="rounded bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 border border-emerald-200">
                          {t.terminalManagement.humanActive}
                        </span>
                      ) : item.human_active === false ? (
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-600 border border-slate-200">
                          {t.terminalManagement.humanInactive}
                        </span>
                      ) : (
                        <span className="text-slate-400">{t.terminalManagement.humanUnlinked}</span>
                      )}
                    </td>
                    <td>
                      {item.fingerprint_count === null ? (
                        <span className="text-amber-700">{t.terminalManagement.fingerprintUnknown}</span>
                      ) : (item.fingerprint_count ?? 0) > 0 ? (
                        <span className="text-emerald-700">{t.terminalManagement.fingerprintPresent}</span>
                      ) : (
                        <span className="text-slate-500">{t.terminalManagement.fingerprintAbsent}</span>
                      )}
                    </td>
                    <td className="text-slate-600">
                      {item.mapping_state === "open"
                        ? t.terminalManagement.mappingOpen
                        : item.mapping_state === "closed"
                        ? t.terminalManagement.mappingClosed
                        : t.terminalManagement.mappingNone}
                    </td>
                    <td>
                      <div className="flex flex-wrap items-center justify-end gap-1.5">
                        <button
                          onClick={() => { setReenrollItem(item); setReenrollStatus("idle"); }}
                          disabled={!canMutate || busyItem === item.device_user_id}
                          className="rounded border border-blue-200 bg-blue-50 px-2 py-1 text-[11px] font-semibold text-blue-700 hover:bg-blue-100 disabled:opacity-40"
                        >
                          {t.terminalManagement.reenrollButton}
                        </button>
                        <button
                          onClick={() => setFpConfirmItem(item)}
                          disabled={!canMutate || busyItem === item.device_user_id || item.fingerprint_count === 0}
                          className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] font-semibold text-amber-700 hover:bg-amber-100 disabled:opacity-40"
                        >
                          {t.terminalManagement.removeFingerprintButton}
                        </button>
                        <button
                          onClick={() => { setAcctConfirmItem(item); setAcctAcknowledge(false); }}
                          disabled={!canMutate || busyItem === item.device_user_id}
                          className="rounded border border-rose-200 bg-rose-50 px-2 py-1 text-[11px] font-semibold text-rose-700 hover:bg-rose-100 disabled:opacity-40"
                        >
                          {t.terminalManagement.removeAccountButton}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Remove fingerprint confirmation */}
      <ConfirmModal
        open={!!fpConfirmItem}
        title={t.terminalManagement.removeFingerprintConfirmTitle}
        tone="danger"
        confirmLabel={t.terminalManagement.removeFingerprintButton}
        busy={busyItem === fpConfirmItem?.device_user_id}
        onConfirm={handleRemoveFingerprint}
        onCancel={() => setFpConfirmItem(null)}
      >
        <div className="text-sm font-semibold text-slate-900">
          {fpConfirmItem?.human_name ?? fpConfirmItem?.device_user_id}
        </div>
        <p className="text-xs text-slate-600 leading-relaxed">{t.terminalManagement.removeFingerprintConfirmBody}</p>
      </ConfirmModal>

      {/* Remove account confirmation */}
      <ConfirmModal
        open={!!acctConfirmItem}
        title={t.terminalManagement.removeAccountConfirmTitle}
        tone="danger"
        confirmLabel={t.terminalManagement.removeAccountButton}
        busy={busyItem === acctConfirmItem?.device_user_id}
        onConfirm={handleRemoveAccount}
        onCancel={() => { setAcctConfirmItem(null); setAcctAcknowledge(false); }}
      >
        <div className="text-sm font-semibold text-slate-900">
          {acctConfirmItem?.human_name ?? acctConfirmItem?.device_user_id}
        </div>
        <p className="text-xs text-slate-600 leading-relaxed">{t.terminalManagement.removeAccountConfirmBody}</p>
        {acctConfirmItem?.human_active === true && acctConfirmItem?.mapping_state === "open" && (
          <div className="rounded-md border border-rose-300 bg-rose-50 p-2.5 text-xs font-semibold text-rose-800">
            {t.terminalManagement.removeAccountActiveWarning}
            <label className="mt-2 flex items-center gap-2 font-normal">
              <input
                type="checkbox"
                checked={acctAcknowledge}
                onChange={(e) => setAcctAcknowledge(e.target.checked)}
              />
              {t.terminalManagement.removeAccountAcknowledgeLabel}
            </label>
          </div>
        )}
      </ConfirmModal>

      {/* Re-enrollment confirmation + progress */}
      <ConfirmModal
        open={!!reenrollItem}
        title={t.terminalManagement.reenrollConfirmTitle}
        tone="primary"
        confirmLabel={t.terminalManagement.reenrollButton}
        busy={reenrollStatus === "pending"}
        onConfirm={handleStartReenroll}
        onCancel={() => { if (reenrollStatus === "idle") setReenrollItem(null); }}
      >
        <div className="text-sm font-semibold text-slate-900">
          {reenrollItem?.human_name ?? reenrollItem?.device_user_id}
        </div>
        {reenrollStatus === "idle" && (
          <>
            <p className="text-xs text-slate-600 leading-relaxed">{t.terminalManagement.reenrollConfirmBody}</p>
            <p className="text-[11px] font-semibold text-amber-800">{t.terminalManagement.reenrollCannotCancelNotice}</p>
          </>
        )}
        {reenrollStatus === "pending" && (
          <p className="text-xs font-semibold text-blue-800">{t.terminalManagement.reenrollInProgress}</p>
        )}
        {reenrollStatus === "confirmed" && (
          <p className="text-xs font-semibold text-emerald-800">{t.terminalManagement.reenrollSuccess}</p>
        )}
        {reenrollStatus === "failed" && (
          <p className="text-xs font-semibold text-rose-800">{t.terminalManagement.reenrollFailed}</p>
        )}
      </ConfirmModal>
    </div>
  );
}
