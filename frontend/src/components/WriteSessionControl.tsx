import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth";
import { useTranslation } from "../i18n";

function formatRemaining(expiresAt: string, now: number): string {
  const ms = new Date(expiresAt).getTime() - now;
  if (ms <= 0) return "00:00";
  const totalSeconds = Math.floor(ms / 1000);
  const mm = Math.floor(totalSeconds / 60)
    .toString()
    .padStart(2, "0");
  const ss = (totalSeconds % 60).toString().padStart(2, "0");
  return `${mm}:${ss}`;
}

/** Compact header badge — visible to every role, read-only. */
export function WriteSessionBadge() {
  const { writeSession, writeSessionActive, serverWriteEnabled } = useAuth();
  const { t } = useTranslation();
  const [now, setNow] = useState(() => Date.now());
  // Both layers must hold for changes to actually be possible — a runtime
  // session can technically still be un-expired in the DB even if the
  // infrastructure master gate was flipped off in the meantime, so the
  // badge must reflect the combined effective state, not Layer 2 alone.
  const effectiveActive = serverWriteEnabled && writeSessionActive;

  useEffect(() => {
    if (!effectiveActive) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [effectiveActive]);

  if (effectiveActive && writeSession?.expires_at) {
    return (
      <span
        title={writeSession.reason ?? undefined}
        className="inline-flex items-center gap-1.5 rounded-md border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-bold text-emerald-800 shadow-2xs"
      >
        <span className="h-2 w-2 rounded-full bg-emerald-600 animate-pulse" />
        {t.writeSession.badgeActive} · {formatRemaining(writeSession.expires_at, now)}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700 shadow-2xs">
      <span className="h-2 w-2 rounded-full bg-slate-500" />
      {t.writeSession.badgeLocked}
    </span>
  );
}

/** Full ADMIN-facing control panel (System page). ADMIN can open/close;
 * every other role sees the same status read-only with no controls, since
 * only ADMIN is authorized to change the write session (enforced server
 * side — this component never grants access on its own). */
export function WriteSessionControl() {
  const { isAdmin, writeSession, writeSessionActive, reload } = useAuth();
  const { t } = useTranslation();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!writeSessionActive) return;
    const interval = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(interval);
  }, [writeSessionActive]);

  async function handleOpen() {
    if (!reason.trim()) return;
    setBusy(true);
    setError(null);
    try {
      await api.openWriteSession(reason.trim());
      setReason("");
      reload();
    } catch (err: any) {
      if (err?.code === "WRITE_SESSION_ALREADY_ACTIVE") {
        setError(t.writeSession.alreadyActive);
      } else if (err?.code === "WRITE_DISABLED") {
        setError(t.personnel.writesDisabledNotice);
      } else {
        setError(`${t.writeSession.openFailed}: ${err?.message ?? ""}`);
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleClose() {
    setBusy(true);
    setError(null);
    try {
      await api.closeWriteSession();
      reload();
    } catch (err: any) {
      setError(err?.message ?? String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-2xs">
      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-500">{t.writeSession.title}</div>

      {writeSessionActive && writeSession ? (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-emerald-600 animate-pulse" />
            <span className="text-sm font-bold text-emerald-800">{t.writeSession.activeTitle}</span>
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600">
            <div>
              <span className="font-semibold text-slate-500">{t.writeSession.openedByLabel}:</span>{" "}
              {writeSession.opened_by_name}
            </div>
            <div>
              <span className="font-semibold text-slate-500">{t.writeSession.remainingLabel}:</span>{" "}
              <span className="font-mono font-bold text-slate-900">
                {writeSession.expires_at ? formatRemaining(writeSession.expires_at, now) : "—"}
              </span>
            </div>
            <div className="col-span-2">
              <span className="font-semibold text-slate-500">{t.writeSession.reasonLabel}:</span> {writeSession.reason}
            </div>
          </div>
          {isAdmin && (
            <button
              onClick={handleClose}
              disabled={busy}
              className="mt-2 inline-flex h-8 items-center justify-center rounded-md border border-rose-300 bg-rose-50 px-3 text-xs font-bold text-rose-800 hover:bg-rose-100 disabled:opacity-50"
            >
              {busy ? t.writeSession.closing : t.writeSession.closeButton}
            </button>
          )}
        </div>
      ) : (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-slate-400" />
            <span className="text-sm font-bold text-slate-700">{t.writeSession.lockedTitle}</span>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">{t.writeSession.lockedBody}</p>
          {isAdmin ? (
            <div className="flex items-center gap-2 pt-1">
              <input
                type="text"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={t.writeSession.reasonPlaceholder}
                className="h-8 flex-1 rounded-md border border-slate-300 px-2 text-xs focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-200"
              />
              <button
                onClick={handleOpen}
                disabled={busy || !reason.trim()}
                className="inline-flex h-8 shrink-0 items-center justify-center rounded-md border border-blue-300 bg-blue-50 px-3 text-xs font-bold text-blue-800 hover:bg-blue-100 disabled:opacity-50"
              >
                {busy ? t.writeSession.opening : t.writeSession.openButton}
              </button>
            </div>
          ) : (
            <p className="text-[11px] text-slate-400">{t.writeSession.adminOnlyHint}</p>
          )}
        </div>
      )}

      {error && <div className="mt-2 text-[11px] font-medium text-rose-700">{error}</div>}
    </div>
  );
}
