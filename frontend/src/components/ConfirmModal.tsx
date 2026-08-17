import type { ReactNode } from "react";
import { useTranslation } from "../i18n";

/** Styled replacement for window.confirm() — used anywhere a destructive or
 * identity-sensitive action needs an explicit "are you sure" step. The body
 * is caller-supplied so each use site controls exactly what evidence is
 * shown (e.g. human-readable names/times only, never raw UUID dumps). */
export function ConfirmModal({
  open,
  title,
  tone = "neutral",
  confirmLabel,
  busy,
  onConfirm,
  onCancel,
  children,
}: {
  open: boolean;
  title: string;
  tone?: "neutral" | "danger" | "primary";
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  if (!open) return null;

  const confirmTone =
    tone === "danger"
      ? "bg-rose-600 hover:bg-rose-700"
      : tone === "primary"
      ? "bg-purple-700 hover:bg-purple-800"
      : "bg-blue-600 hover:bg-blue-700";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-md rounded-lg border border-slate-200 bg-white p-5 shadow-xl">
        <h2 className="text-sm font-bold text-slate-900">{title}</h2>
        <div className="mt-3 space-y-1.5 text-xs text-slate-700 leading-relaxed">{children}</div>
        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={busy}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            {t.common.cancel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={busy}
            className={`rounded-md px-3 py-1.5 text-xs font-bold text-white shadow-xs disabled:opacity-50 ${confirmTone}`}
          >
            {busy ? t.common.saving : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
