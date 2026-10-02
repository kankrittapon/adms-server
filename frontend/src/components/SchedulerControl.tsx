import { useState } from "react";
import { api } from "../api/client";
import { useAuth } from "../auth";
import { Badge, ErrorBanner, Loading } from "./Status";
import { useApi } from "../hooks/useApi";
import { useTranslation } from "../i18n";
import { friendlyApiError } from "../i18n/apiErrors";

export function SchedulerControl() {
  const { me, isAdmin } = useAuth();
  const { t } = useTranslation();
  const settings = useApi((s) => api.getScheduleSettings(s), []);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  // Also need writeSession for badge logic (Manual vs Locked)
  const { writeSessionActive } = useAuth();

  async function handleToggle(nextEnabled: boolean) {
    setBusy(true);
    setMsg(null);
    try {
      await api.updateScheduleSettings(nextEnabled);
      await settings.reload();
      setMsg({ tone: "ok", text: t.system.schedulerUpdateSuccess });
    } catch (err) {
      setMsg({ tone: "err", text: friendlyApiError(err, t) || t.system.schedulerUpdateFailed });
    } finally {
      setBusy(false);
    }
  }

  const enabled = settings.data?.enabled ?? false;
  const activeWindow = settings.data?.active_window;

  // Badge logic: Active Window (Auto) = enabled && activeWindow.active && opened_by SYSTEM_SCHEDULER
  // For simplicity, if enabled && activeWindow.active, show Active Window, else if enabled && !active show enabled badge, else Manual/Locked
  let badge: { tone: "green" | "amber" | "neutral" | "purple"; label: string };
  if (settings.loading) {
    badge = { tone: "neutral", label: t.common.loading };
  } else if (settings.error) {
    badge = { tone: "neutral", label: t.system.schedulerLoadError };
  } else if (enabled && activeWindow?.active) {
    badge = { tone: "green", label: t.system.schedulerActiveWindowBadge };
  } else if (enabled) {
    badge = { tone: "amber", label: t.system.schedulerEnabledBadge };
  } else if (writeSessionActive) {
    badge = { tone: "amber", label: t.system.schedulerManualBadge };
  } else {
    badge = { tone: "neutral", label: t.system.schedulerLockedBadge };
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
      <div className="border-b border-slate-100 pb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-slate-900">{t.system.schedulerTitle}</h2>
          <p className="mt-0.5 text-xs text-slate-500">{t.system.schedulerSubtitle}</p>
        </div>
        <Badge tone={badge.tone}>{badge.label}</Badge>
      </div>

      {settings.error && (
        <ErrorBanner message={settings.error} />
      )}

      {msg && (
        <div
          className={`rounded-md border p-3 text-xs font-medium ${
            msg.tone === "ok"
              ? "border-emerald-300 bg-emerald-50 text-emerald-900"
              : "border-rose-300 bg-rose-50 text-rose-900"
          }`}
        >
          {msg.text}
        </div>
      )}

      {settings.loading ? (
        <Loading />
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 p-4">
            <div className="space-y-1">
              <div className="text-sm font-semibold text-slate-900">{t.system.schedulerToggleLabel}</div>
              <div className="text-xs text-slate-500">{t.system.schedulerToggleHint}</div>
              {settings.data && (
                <div className="text-[11px] text-slate-400">
                  {settings.data.days} {settings.data.start_time}–{settings.data.end_time} {settings.data.timezone}
                  {settings.data.updated_by_name ? ` • by ${settings.data.updated_by_name}` : ""}
                </div>
              )}
            </div>
            <div className="flex items-center gap-3">
              <span className="text-xs font-medium text-slate-600">
                {enabled ? t.system.schedulerToggleOn : t.system.schedulerToggleOff}
              </span>
              <label className="relative inline-flex cursor-pointer items-center" title={!isAdmin ? t.system.schedulerAdminOnlyHint : undefined}>
                <input
                  type="checkbox"
                  checked={enabled}
                  disabled={!isAdmin || busy || settings.loading}
                  onChange={(e) => handleToggle(e.target.checked)}
                  className="peer sr-only"
                />
                <div
                  className={`peer h-6 w-11 rounded-full bg-slate-200 transition-colors
                    peer-checked:bg-emerald-600 peer-focus:ring-2 peer-focus:ring-emerald-300
                    peer-disabled:cursor-not-allowed peer-disabled:opacity-40
                    after:absolute after:left-[2px] after:top-[2px] after:h-5 after:w-5 after:rounded-full after:bg-white after:transition-all after:content-[''] peer-checked:after:translate-x-5`}
                />
              </label>
            </div>
          </div>

          {settings.data && (
            <LastRunLine lastRun={settings.data.last_run} enabled={enabled} />
          )}

          {!isAdmin && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-2.5 text-xs text-amber-800">
              {t.system.schedulerAdminOnlyHint}
            </div>
          )}

          {isAdmin && (
            <div className="text-[11px] text-slate-400">
              {t.system.adminOnlyBadge} • {me?.username ?? ""}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// A weekday run happens at least every ~15h (09:00 open / 18:00 close); more
// than 3 days without one means the host timer is not reaching the API.
const STALE_MS = 3 * 24 * 60 * 60 * 1000;

function LastRunLine({
  lastRun,
  enabled,
}: {
  lastRun: { action: string; result: string; at: string } | null;
  enabled: boolean;
}) {
  const { t } = useTranslation();
  const stale = !lastRun || Date.now() - new Date(lastRun.at).getTime() > STALE_MS;
  const warn = enabled && stale;
  return (
    <div
      className={`rounded-md border p-2.5 text-xs ${
        warn ? "border-rose-300 bg-rose-50 text-rose-900" : "border-slate-200 bg-white text-slate-600"
      }`}
    >
      {t.system.schedulerLastRun}:{" "}
      {lastRun
        ? `${new Date(lastRun.at).toLocaleString()} (${lastRun.action} — ${lastRun.result})`
        : t.system.schedulerNeverRun}
      {warn && <div className="mt-1 font-semibold">{t.system.schedulerStaleWarning}</div>}
    </div>
  );
}
