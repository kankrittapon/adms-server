import { useRef, useState } from "react";
import { api, ApiClientError } from "../api/client";
import { useTranslation } from "../i18n";
import type { CsvImportPreview } from "../api/types";

/**
 * ADMS-Personnel-MasterData-024 Phase 7: strict preview-then-commit flow.
 * The file is NEVER written to the database on selection/preview — only
 * classify_csv_rows() runs. Commit re-uploads and re-validates the same
 * file server-side before writing (never trusts a stale client preview).
 */
export function CsvImportModal({ onClose, onCommitted }: { onClose: () => void; onCommitted: () => void }) {
  const { t } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<CsvImportPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [committed, setCommitted] = useState<{ created: number; updated: number } | null>(null);

  async function handleFileChosen(f: File) {
    setFile(f);
    setPreview(null);
    setError(null);
    setBusy(true);
    try {
      const result = await api.previewHumansImport(f);
      setPreview(result);
    } catch (err) {
      if (err instanceof ApiClientError && err.code === "CSV_MALFORMED") {
        setError(t.personnel.csvMalformedBody);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setBusy(false);
    }
  }

  async function handleCommit() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.commitHumansImport(file);
      setCommitted({ created: result.created, updated: result.updated });
      onCommitted();
    } catch (err) {
      if (err instanceof ApiClientError && (err.code === "WRITE_DISABLED" || err.code === "WRITE_SESSION_REQUIRED" || err.code === "WRITE_SESSION_EXPIRED")) {
        setError(t.personnel.writesDisabledNotice);
      } else {
        setError(err instanceof Error ? err.message : String(err));
      }
    } finally {
      setBusy(false);
    }
  }

  async function downloadTemplate() {
    const blob = await api.importTemplateCsv();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "personnel_import_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  const errorRows = (preview?.rows ?? []).filter((r) => r.classification === "ERROR");
  const warningRows = (preview?.rows ?? []).filter((r) => r.warning_th);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl space-y-4 max-h-[85vh] overflow-y-auto">
        <div className="text-sm font-bold text-slate-900">{t.personnel.importCsvTitle}</div>

        {committed ? (
          <div className="space-y-3">
            <div className="rounded-md border border-emerald-300 bg-emerald-50 p-3 text-xs font-semibold text-emerald-900">
              ✓ {t.personnel.importCommittedMessage
                .replace("{created}", String(committed.created))
                .replace("{updated}", String(committed.updated))}
            </div>
            <button
              onClick={onClose}
              className="rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700"
            >
              {t.common.close}
            </button>
          </div>
        ) : (
          <>
            <button
              type="button"
              onClick={downloadTemplate}
              className="text-xs font-semibold text-blue-600 hover:underline"
            >
              {t.personnel.downloadTemplateButton}
            </button>

            <div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,text/csv"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleFileChosen(f);
                }}
                disabled={busy}
                className="w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs"
              />
            </div>

            {error && (
              <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-xs text-rose-800">{error}</div>
            )}

            {preview && (
              <div className="space-y-3">
                <div className="grid grid-cols-4 gap-2 text-center text-xs">
                  <div className="rounded-md border border-blue-200 bg-blue-50 p-2">
                    <div className="text-lg font-bold text-blue-800">{preview.summary.new}</div>
                    <div className="text-[10px] text-blue-700">{t.personnel.csvNewLabel}</div>
                  </div>
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-2">
                    <div className="text-lg font-bold text-amber-800">{preview.summary.update}</div>
                    <div className="text-[10px] text-amber-700">{t.personnel.csvUpdateLabel}</div>
                  </div>
                  <div className="rounded-md border border-slate-200 bg-slate-50 p-2">
                    <div className="text-lg font-bold text-slate-700">{preview.summary.unchanged}</div>
                    <div className="text-[10px] text-slate-500">{t.personnel.csvUnchangedLabel}</div>
                  </div>
                  <div className="rounded-md border border-rose-200 bg-rose-50 p-2">
                    <div className="text-lg font-bold text-rose-800">{preview.summary.error}</div>
                    <div className="text-[10px] text-rose-700">{t.personnel.csvErrorLabel}</div>
                  </div>
                </div>

                {errorRows.length > 0 && (
                  <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900 space-y-1">
                    {errorRows.map((r) => (
                      <div key={r.row_number}>{r.reason_th}</div>
                    ))}
                  </div>
                )}

                {warningRows.length > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 space-y-1">
                    {warningRows.map((r) => (
                      <div key={r.row_number}>{r.warning_th}</div>
                    ))}
                  </div>
                )}

                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={onClose}
                    disabled={busy}
                    className="rounded-md border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    {t.common.cancel}
                  </button>
                  <button
                    type="button"
                    onClick={handleCommit}
                    disabled={busy || (preview.summary.new === 0 && preview.summary.update === 0)}
                    className="rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 disabled:opacity-50"
                  >
                    {busy ? t.common.saving : t.personnel.confirmImportButton}
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
