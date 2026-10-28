import { useRef, useState } from "react";
import { api, ApiClientError } from "../api/client";
import { useTranslation } from "../i18n";
import { friendlyApiError } from "../i18n/apiErrors";
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
  const [committed, setCommitted] = useState<{
    created: number;
    updated: number;
    renamed: number;
    failed: number;
    left: number;
    leftFailed: string[];
  } | null>(null);
  // People in ADMS but not in an exported file: leave candidates the
  // personnel officer ticks explicitly — never closed automatically.
  const [leaving, setLeaving] = useState<Set<string>>(new Set());
  const [leaveReason, setLeaveReason] = useState("ย้ายออก");

  async function handleFileChosen(f: File) {
    setFile(f);
    setPreview(null);
    setLeaving(new Set());
    setError(null);
    setBusy(true);
    try {
      const result = await api.previewHumansImport(f);
      setPreview(result);
    } catch (err) {
      if (err instanceof ApiClientError && err.code === "CSV_MALFORMED") {
        setError(t.personnel.csvMalformedBody);
      } else {
        setError(friendlyApiError(err, t));
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
      const hasRows = !!preview && (preview.summary.new > 0 || preview.summary.update > 0);
      const result = hasRows ? await api.commitHumansImport(file) : null;
      const leftFailed: string[] = [];
      let left = 0;
      for (const m of preview?.missing ?? []) {
        if (!leaving.has(m.employee_id)) continue;
        const name = `${m.rank ?? ""} ${m.display_name}`.trim();
        try {
          await api.deactivateHuman(m.employee_id, leaveReason.trim() || "ย้ายออก");
          left++;
          const r = await api.removeFromScanner(m.employee_id);
          if (r.failed.length) leftFailed.push(name);
        } catch {
          leftFailed.push(name);
        }
      }
      setCommitted({
        created: result?.created ?? 0,
        updated: result?.updated ?? 0,
        renamed: result?.terminal_name_sync?.renamed ?? 0,
        failed: result?.terminal_name_sync?.failed ?? 0,
        left,
        leftFailed,
      });
      onCommitted();
    } catch (err) {
      if (err instanceof ApiClientError && (err.code === "WRITE_DISABLED" || err.code === "WRITE_SESSION_REQUIRED" || err.code === "WRITE_SESSION_EXPIRED")) {
        setError(t.personnel.writesDisabledNotice);
      } else {
        setError(friendlyApiError(err, t));
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
            {(committed.renamed > 0 || committed.failed > 0) && (
              <div
                className={`rounded-md border p-3 text-xs font-semibold ${
                  committed.failed ? "border-amber-300 bg-amber-50 text-amber-900" : "border-emerald-300 bg-emerald-50 text-emerald-900"
                }`}
              >
                {t.workflow.namesSyncedResult
                  .replace("{renamed}", String(committed.renamed))
                  .replace("{failed}", String(committed.failed))}
              </div>
            )}
            {(committed.left > 0 || committed.leftFailed.length > 0) && (
              <div
                className={`rounded-md border p-3 text-xs font-semibold ${
                  committed.leftFailed.length ? "border-amber-300 bg-amber-50 text-amber-900" : "border-emerald-300 bg-emerald-50 text-emerald-900"
                }`}
              >
                ย้ายออกแล้ว {committed.left} คน
                {committed.leftFailed.length > 0 &&
                  ` · ยังลบจากเครื่องสแกนไม่สำเร็จ: ${committed.leftFailed.join(", ")} (เปิดหน้าคนนั้นแล้วกด "ลบออกจากเครื่องอีกครั้ง")`}
              </div>
            )}
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

                {(preview.missing ?? []).length > 0 && (
                  <MissingPeople
                    missing={preview.missing ?? []}
                    inFile={preview.rows.length}
                    leaving={leaving}
                    setLeaving={setLeaving}
                    reason={leaveReason}
                    setReason={setLeaveReason}
                  />
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
                    disabled={busy || (preview.summary.new === 0 && preview.summary.update === 0 && leaving.size === 0)}
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

type MissingPerson = { employee_id: string; display_name: string; rank?: string | null; branch?: string | null };

function MissingPeople({
  missing,
  inFile,
  leaving,
  setLeaving,
  reason,
  setReason,
}: {
  missing: MissingPerson[];
  inFile: number;
  leaving: Set<string>;
  setLeaving: (s: Set<string>) => void;
  reason: string;
  setReason: (s: string) => void;
}) {
  const suspicious = missing.length > 0.2 * (missing.length + inFile);
  const toggle = (id: string) => {
    const next = new Set(leaving);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setLeaving(next);
  };
  return (
    <div className="rounded-md border border-slate-300 bg-slate-50 p-3 text-xs space-y-2">
      <div className="font-bold text-slate-900">ไม่อยู่ในไฟล์ {missing.length} คน — ย้ายออกหรือไม่?</div>
      <p className="text-[11px] text-slate-600">
        ติ๊กเฉพาะคนที่ย้ายออก/พ้นหน่วยจริง ระบบจะปิดชื่อและลบลายนิ้วมือออกจากเครื่องสแกนเมื่อกดยืนยัน · คนที่ไม่ติ๊กจะไม่ถูกแตะ
      </p>
      {suspicious && (
        <p className="rounded bg-amber-100 px-2 py-1 font-semibold text-amber-900">
          ⚠️ หายจากไฟล์เกิน 20% — ไฟล์อาจไม่ครบ (เช่น ส่งออกเฉพาะบางแผนก) ตรวจให้แน่ใจก่อนติ๊ก
        </p>
      )}
      <div className="max-h-48 overflow-auto rounded border border-slate-200 bg-white">
        {missing.map((m) => (
          <label key={m.employee_id} className="flex cursor-pointer items-center gap-2 border-b border-slate-100 px-2 py-1 last:border-0">
            <input type="checkbox" checked={leaving.has(m.employee_id)} onChange={() => toggle(m.employee_id)} />
            <span className="font-semibold">{`${m.rank ?? ""} ${m.display_name}`.trim()}</span>
            <span className="text-slate-500">{m.branch ?? ""}</span>
          </label>
        ))}
      </div>
      {leaving.size > 0 && (
        <div className="flex items-center gap-2">
          <span className="font-semibold text-rose-700">ย้ายออก {leaving.size} คน · เหตุผล</span>
          <input
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="flex-1 rounded border border-slate-300 bg-white px-2 py-1"
          />
        </div>
      )}
    </div>
  );
}
