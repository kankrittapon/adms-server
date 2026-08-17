import { useState } from "react";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatusBadge } from "../components/Status";
import { ConfirmModal } from "../components/ConfirmModal";
import { useTranslation } from "../i18n";
import { verificationMethodLabels, enumLabel } from "../i18n/enumLabels";
import type { MappingEligibilityItem } from "../api/types";

export function Mappings() {
  const { isAdmin } = useAuth();
  const { t, locale } = useTranslation();
  const { data, loading, error, reload } = useApi((s) => api.mappings({ limit: 100 }, s), []);

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex flex-col justify-between gap-3 border-b border-slate-200 pb-4 sm:flex-row sm:items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.mappings.title}</h1>
          <p className="text-xs text-slate-500">{t.mappings.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="rounded-md border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 shadow-2xs">
            {data ? `${data.total} ${t.mappings.verifiedMappings}` : t.common.loading}
          </span>
        </div>
      </div>

      {isAdmin && <CreateMappingPanel onCreated={reload} />}

      {/* Main Mappings Table */}
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
                  <th className="w-16">Map ID</th>
                  <th>{t.personnel.thaiName}</th>
                  <th>{t.attendance.terminalIdColumn}</th>
                  <th>{t.common.status}</th>
                  <th>{t.mappings.validFrom} (UTC)</th>
                  <th>{t.mappings.validTo} (UTC)</th>
                  <th>Verification Method</th>
                  <th>{t.mappings.verifiedBy}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data?.items.map((m) => (
                  <tr key={m.mapping_id} className="transition-colors hover:bg-slate-50/80">
                    <td className="font-mono font-bold text-blue-600">#{m.mapping_id}</td>
                    <td className="font-semibold text-slate-900">
                      {m.employee_name ?? m.employee_id.slice(0, 8)}
                    </td>
                    <td className="font-mono text-slate-700">{m.device_user_id ?? m.device_user_pk}</td>
                    <td>
                      <StatusBadge status={m.mapping_status} />
                    </td>
                    <td className="font-mono text-slate-700 whitespace-nowrap">{fmt(m.valid_from)}</td>
                    <td className="font-mono text-slate-500 whitespace-nowrap">
                      {m.valid_to ? fmt(m.valid_to) : `— (${t.mappings.activeMapping})`}
                    </td>
                    <td>
                      <span className="inline-block rounded bg-purple-50 px-2 py-0.5 text-[11px] font-semibold text-purple-700 border border-purple-200">
                        {m.verification_method ? enumLabel(verificationMethodLabels, m.verification_method, locale) : "—"}
                      </span>
                    </td>
                    <td className="font-medium text-slate-800">{m.verified_by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-slate-100 bg-slate-50/60 px-4 py-2 text-[11px] text-slate-500">
            {t.mappings.temporalFooterNote}
          </div>
        </div>
      )}
    </div>
  );
}

function fmt(iso: string): string {
  return iso.replace("T", " ").slice(0, 19);
}

function CreateMappingPanel({ onCreated }: { onCreated: () => void }) {
  const { t } = useTranslation();
  const { me, canMutate } = useAuth();
  const elig = useApi((s) => api.mappingEligibility(s), []);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [verifiedBy, setVerifiedBy] = useState(me?.username ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const item: MappingEligibilityItem | null =
    elig.data?.items.find((e) => e.enrollment_id === selectedId) ?? null;

  function requestSubmit() {
    if (!item || !verifiedBy.trim() || !note.trim()) {
      setError("Select an eligible enrollment, and fill verified_by + note.");
      return;
    }
    setError(null);
    setConfirmOpen(true);
  }

  function confirmSubmit() {
    if (!item) return;
    setBusy(true);
    setError(null);
    api
      .createMapping({
        employee_id: item.employee_id,
        device_user_pk: item.device_user_pk!,
        enrollment_id: item.enrollment_id,
        controlled_attendance_id: item.controlled_attendance_id!,
        verified_by: verifiedBy.trim(),
        verification_note: note.trim(),
      })
      .then(() => {
        setSelectedId(null);
        setNote("");
        setConfirmOpen(false);
        elig.reload();
        onCreated();
      })
      .catch((e: unknown) => {
        setConfirmOpen(false);
        if (e instanceof ApiClientError && (e.code === "WRITE_DISABLED" || e.code === "WRITE_SESSION_REQUIRED")) {
          setError(t.enrollment.writeSessionLockedBody);
        } else if (e instanceof ApiClientError && e.code === "WRITE_SESSION_EXPIRED") {
          setError(t.enrollment.writeSessionExpiredMidWorkflow);
        } else if (e instanceof ApiClientError) {
          setError(`${e.code}: ${e.message}`);
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => setBusy(false));
  }

  return (
    <div className="rounded-lg border border-purple-200 bg-purple-50/40 p-5 shadow-2xs space-y-4">
      <div className="flex items-center justify-between border-b border-purple-100 pb-3">
        <div>
          <h2 className="text-sm font-bold text-slate-900">{t.mappings.adminAuthorityTitle}</h2>
          <p className="mt-0.5 text-xs text-slate-500">
            {t.mappings.adminAuthorityDesc}
          </p>
        </div>
        <span className="rounded bg-purple-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-purple-800">
          Admin Action
        </span>
      </div>

      {!canMutate && (
        <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs font-semibold text-amber-800">
          {t.enrollment.writeSessionLockedBody}
        </div>
      )}

      {error && <ErrorBanner message={error} />}

      {elig.loading ? (
        <Loading />
      ) : elig.error ? (
        <ErrorBanner message={elig.error} />
      ) : elig.data?.items.length === 0 ? (
        <p className="text-xs text-slate-500">
          No eligible enrollments awaiting activation.
        </p>
      ) : (
        <div className="space-y-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <div>
              <label className="block text-[11px] font-bold text-slate-700">
                Eligible Enrollment (READY_FOR_MAPPING)
              </label>
              <select
                value={selectedId ?? ""}
                onChange={(e) => {
                  setSelectedId(e.target.value ? Number(e.target.value) : null);
                  setError(null);
                }}
                disabled={!canMutate || busy}
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-purple-600 focus:outline-none focus:ring-1 focus:ring-purple-600 disabled:bg-slate-100"
              >
                <option value="">— Select eligible session —</option>
                {elig.data?.items.map((e) => (
                  <option key={e.enrollment_id} value={e.enrollment_id}>
                    #{e.enrollment_id} · {e.employee_name ?? e.employee_id.slice(0, 8)} · Terminal User {e.reserved_device_user_id}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-[11px] font-bold text-slate-700">{t.mappings.verifiedBy}</label>
              <input
                type="text"
                value={verifiedBy}
                disabled={!canMutate || busy}
                onChange={(e) => setVerifiedBy(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-purple-600 focus:outline-none focus:ring-1 focus:ring-purple-600 disabled:bg-slate-100"
              />
            </div>

            <div>
              <label className="block text-[11px] font-bold text-slate-700">Verification Note</label>
              <input
                type="text"
                value={note}
                disabled={!canMutate || busy}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Reference evidence log & physical check"
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-purple-600 focus:outline-none focus:ring-1 focus:ring-purple-600 disabled:bg-slate-100"
              />
            </div>
          </div>

          {item && (
            <div className="rounded-lg border border-purple-200 bg-white p-3.5 text-xs text-purple-950 shadow-2xs space-y-1">
              <div>
                <strong>Human:</strong> {item.employee_name} (<code className="font-mono">{item.employee_id}</code>)
              </div>
              <div>
                <strong>Terminal Account:</strong> User ID {item.device_user_id} (PK {item.device_user_pk}) · Device: {item.device_name}
              </div>
              <div>
                <strong>Controlled Scan Evidence:</strong> Scan at {item.controlled_scan_time ? fmt(item.controlled_scan_time) : "—"} · Attendance ID #{item.controlled_attendance_id ?? "?"}
              </div>
            </div>
          )}

          <div className="pt-1">
            <button
              onClick={requestSubmit}
              disabled={!canMutate || busy || !selectedId}
              className="rounded-md bg-purple-700 px-4 py-2 text-xs font-bold text-white shadow-xs transition-colors hover:bg-purple-800 focus:outline-none focus:ring-2 focus:ring-purple-600 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
            >
              {busy ? t.common.saving : t.mappings.createMappingButton}
            </button>
          </div>
        </div>
      )}

      {item && (
        <ConfirmModal
          open={confirmOpen}
          title={t.mappings.confirmTitle}
          tone="primary"
          confirmLabel={t.mappings.createMappingButton}
          busy={busy}
          onConfirm={confirmSubmit}
          onCancel={() => setConfirmOpen(false)}
        >
          <div>
            <span className="font-semibold text-slate-500">{t.mappings.confirmPersonLabel}:</span>{" "}
            <strong>{item.employee_name ?? "—"}</strong>
          </div>
          <div>
            <span className="font-semibold text-slate-500">{t.mappings.confirmTerminalLabel}:</span>{" "}
            <strong>{item.device_name ?? "—"}</strong>
          </div>
          <div>
            <span className="font-semibold text-slate-500">{t.mappings.confirmScanLabel}:</span>{" "}
            <strong>{item.controlled_scan_time ? fmt(item.controlled_scan_time) : "—"}</strong>
          </div>
          <p className="pt-2 text-[11px] text-slate-500 leading-relaxed">{t.mappings.confirmWarning}</p>
        </ConfirmModal>
      )}
    </div>
  );
}
