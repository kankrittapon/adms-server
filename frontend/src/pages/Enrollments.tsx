import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { useApi } from "../hooks/useApi";
import { useAttendanceStream } from "../hooks/useAttendanceStream";
import { ErrorBanner, Loading, StatusBadge, StreamStatusBadge } from "../components/Status";
import { WriteSessionBadge } from "../components/WriteSessionControl";
import { useTranslation } from "../i18n";
import { computeTerminalNamePreview } from "../lib/terminalName";
import type { Enrollment, EnrollmentNextActions } from "../api/types";

function getStepIndex(status: string): number {
  switch (status) {
    case "RESERVED":
      return 0;
    case "TERMINAL_ACCOUNT_CREATED":
    case "FINGERPRINT_ENROLLMENT_PENDING":
      return 1;
    case "FINGERPRINT_ENROLLED":
    case "CONTROLLED_SCAN_PENDING":
      return 2;
    case "CONTROLLED_SCAN_CONFIRMED":
      return 3;
    case "READY_FOR_MAPPING":
      return 4;
    case "RETIRED":
      return 5;
    case "CANCELLED":
      return -1;
    default:
      return 0;
  }
}

export function Enrollments() {
  const { me, serverWriteEnabled, writeSessionActive, canMutate } = useAuth();
  const { t } = useTranslation();
  const list = useApi((s) => api.enrollments({ limit: 100 }, s), []);
  // Active Enrollment Queue policy: ADMS-UX-CrossLifecycleClosure-021B —
  // filter on the server-derived `lifecycle_state`, never on raw `status`
  // alone. A raw-status filter (e.g. status !== 'RETIRED') misses the real
  // production case where an enrollment's mapping was later closed by
  // terminal removal but its own `status` column is still whatever it was
  // at mapping-creation time — lifecycle_state is derived fresh from
  // current facts every read, so this can never drift out of sync.
  const historyItems = (list.data?.items ?? []).filter((e) => e.lifecycle_state !== "IN_PROGRESS");
  const activeItems = (list.data?.items ?? []).filter((e) => e.lifecycle_state === "IN_PROGRESS");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [terminalAccountUncertain, setTerminalAccountUncertain] = useState(false);

  const STEPS = [
    { id: "RESERVED", label: t.enrollment.step1Title },
    { id: "TERMINAL_ACCOUNT_CREATED", label: t.enrollment.step2Title },
    { id: "FINGERPRINT_ENROLLED", label: t.enrollment.step3Title },
    { id: "CONTROLLED_SCAN_CONFIRMED", label: t.enrollment.step4Title },
    { id: "READY_FOR_MAPPING", label: t.enrollment.step5Title },
    { id: "RETIRED", label: t.enrollment.step6Title },
  ];

  // Auto-select the first or newest active (non-terminal) enrollment if
  // none is selected. Also fires after a cancel clears selectedId, so the
  // workspace lands on another active session instead of staying empty.
  useEffect(() => {
    if (selectedId === null && activeItems.length > 0) {
      setSelectedId(activeItems[0].enrollment_id);
    }
  }, [activeItems, selectedId]);

  // The selected session must itself be looked up from the full list (not
  // activeItems) so a just-cancelled session already showing in the
  // inspector can still render its terminal state for one final frame
  // before selectedId is cleared — see the cancel success handler below.
  const selected: Enrollment | null =
    list.data?.items.find((e) => e.enrollment_id === selectedId) ?? null;

  const nextActions = useApi<EnrollmentNextActions | null>(
    (s) => (selectedId ? api.enrollmentNextActions(selectedId, s) : Promise.resolve(null)),
    [selectedId]
  );

  return (
    <div className="space-y-6">
      {/* Workspace Header */}
      <div className="flex flex-col justify-between gap-2 border-b border-slate-200 pb-4 md:flex-row md:items-center">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.enrollment.title}</h1>
          <p className="text-xs text-slate-500">{t.enrollment.subtitle}</p>
        </div>
        <div className="flex items-center gap-2">
          <WriteSessionBadge />
        </div>
      </div>

      {/* Proactive write-session banner — plain language, no infra jargon */}
      {!(serverWriteEnabled && writeSessionActive) && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3.5 text-xs text-amber-900 shadow-2xs">
          <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-200 font-bold text-amber-900">
            !
          </div>
          <div>
            <div className="font-bold">{t.enrollment.writeSessionLockedTitle}</div>
            <div className="mt-0.5 text-amber-800 leading-relaxed">
              {t.enrollment.writeSessionLockedBody}
            </div>
          </div>
        </div>
      )}

      {actionError && <ErrorBanner message={actionError} />}
      {actionSuccess && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-xs font-medium text-emerald-800 shadow-2xs">
          {actionSuccess}
        </div>
      )}

      {/* Step 1: Start New Enrollment (Reserve) */}
      <ReserveCard
        operatorName={me?.username ?? ""}
        canMutate={canMutate}
        onReserved={(newId) => {
          setActionError(null);
          setActionSuccess(t.enrollment.reserveSuccessMessage);
          list.reload();
          setSelectedId(newId);
        }}
      />

      {/* Main Workspace Split: Enrollment List & Active Step Inspector */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Col: Enrollment Queue (5 cols) */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              {t.enrollment.activeQueue} ({activeItems.length})
            </h2>
            <button
              onClick={() => list.reload()}
              className="text-[11px] font-medium text-blue-600 hover:underline"
            >
              {t.common.refresh}
            </button>
          </div>

          {list.loading ? (
            <Loading />
          ) : list.error ? (
            <ErrorBanner message={list.error} />
          ) : activeItems.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-xs text-slate-500">
              {t.enrollment.noActiveSessions}
            </div>
          ) : (
            <div className="space-y-2">
              {activeItems.map((e) => {
                const isSelected = selectedId === e.enrollment_id;
                const stepIdx = getStepIndex(e.status);
                return (
                  <div
                    key={e.enrollment_id}
                    onClick={() => {
                      setSelectedId(e.enrollment_id);
                      setActionError(null);
                      setActionSuccess(null);
                      setTerminalAccountUncertain(false);
                    }}
                    className={`cursor-pointer rounded-lg border p-3.5 text-xs transition-all ${
                      isSelected
                        ? "border-blue-500 bg-blue-50/60 shadow-xs ring-1 ring-blue-500"
                        : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/70"
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="font-bold text-slate-900">
                          {e.employee_name ?? e.employee_id.slice(0, 8)}
                        </div>
                        <div className="mt-0.5 font-mono text-[11px] text-slate-500">
                          ID #{e.enrollment_id} · Terminal User{" "}
                          <span className="font-bold text-slate-800">{e.reserved_device_user_id}</span>
                        </div>
                      </div>
                      <StatusBadge status={e.status} />
                    </div>

                    <div className="mt-2.5 flex items-center justify-between border-t border-slate-100 pt-2 text-[11px] text-slate-500">
                      <span>By: {e.reserved_by ?? "—"}</span>
                      <span>
                        {stepIdx >= 0 ? `Step ${stepIdx + 1} / 6` : t.enrollment.cancelledTitle}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* ADMS-UX-CrossLifecycleClosure-021B: completed/cancelled/removed
              enrollments are visually separated and non-actionable — never
              clickable into the mutable inspector, so a historical record
              can never accidentally become "the selected active workflow"
              merely because it's the newest row. */}
          {historyItems.length > 0 && (
            <div className="pt-2">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                {t.enrollment.historyTitle} ({historyItems.length})
              </h3>
              <div className="mt-2 space-y-1.5">
                {historyItems.map((e) => (
                  <div
                    key={e.enrollment_id}
                    className="rounded-lg border border-slate-150 bg-slate-50/60 p-3 text-xs opacity-80"
                  >
                    <div className="flex items-start justify-between">
                      <div>
                        <div className="font-semibold text-slate-700">
                          {e.employee_name ?? e.employee_id.slice(0, 8)}
                        </div>
                        <div className="mt-0.5 font-mono text-[11px] text-slate-400">
                          Terminal User <span className="font-bold text-slate-600">{e.reserved_device_user_id}</span>
                        </div>
                      </div>
                      <span className="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase text-slate-500 bg-slate-200">
                        {e.lifecycle_state === "COMPLETED"
                          ? t.enrollment.completedTitle
                          : e.lifecycle_state === "REMOVED_FROM_TERMINAL"
                          ? t.enrollment.removedFromTerminalLabel
                          : t.enrollment.cancelledTitle}
                      </span>
                    </div>
                    <div className="mt-1.5 text-[10px] text-slate-400">{t.enrollment.historyPreservedNote}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Col: Active Enrollment Inspector & Guided Stepper (7 cols) */}
        <div className="lg:col-span-7">
          {selected ? (
            <ActiveEnrollmentInspector
              enrollment={selected}
              steps={STEPS}
              canMutate={canMutate}
              busyAction={busyAction}
              terminalAccountUncertain={terminalAccountUncertain}
              onRunAction={async (action, payload) => {
                setBusyAction(action);
                setActionError(null);
                setActionSuccess(null);
                try {
                  if (action === "create-terminal-account") {
                    const res = await api.createTerminalAccount(
                      selected.enrollment_id,
                      payload.display_name as string,
                      me?.username ?? "operator"
                    );
                    setActionSuccess(
                      res.reconciled ? t.enrollment.terminalReconciledSuccess : t.enrollment.terminalCreatedSuccess
                    );
                    setTerminalAccountUncertain(false);
                  } else if (action === "start-fingerprint-enrollment") {
                    await api.startFingerprintEnrollment(selected.enrollment_id, me?.username ?? "operator");
                    setActionSuccess(t.enrollment.fingerprintWindowActiveMessage);
                  } else if (action === "confirm-fingerprint") {
                    await api.confirmFingerprintEnrolled(selected.enrollment_id, me?.username ?? "operator");
                    setActionSuccess(t.enrollment.fingerprintConfirmedMessage);
                  } else if (action === "start-controlled-scan") {
                    await api.startControlledScan(selected.enrollment_id, me?.username ?? "operator");
                    setActionSuccess(t.enrollment.scanWindowStartedMessage);
                  } else if (action === "confirm-controlled-scan") {
                    await api.confirmControlledScan(selected.enrollment_id, me?.username ?? "operator");
                    setActionSuccess(t.enrollment.scanConfirmedMessage);
                  } else if (action === "mark-ready-for-mapping") {
                    await api.markReadyForMapping(selected.enrollment_id, me?.username ?? "operator");
                    setActionSuccess(t.enrollment.readyForMappingSuccessMessage);
                  } else if (action === "cancel") {
                    await api.cancelEnrollment(selected.enrollment_id, me?.username ?? "operator", payload.notes as string);
                    setActionSuccess(t.enrollment.cancelSuccessMessage);
                    // The session is now terminal — clear selection so the
                    // workspace lands on the next active session instead of
                    // continuing to show a now-frozen inspector, and it can
                    // no longer be re-selected once activeItems excludes it.
                    setSelectedId(null);
                  }
                  list.reload();
                  nextActions.reload();
                } catch (err: unknown) {
                  if (action === "create-terminal-account" && err instanceof ApiClientError) {
                    if (err.code === "TERMINAL_ACCOUNT_CONFLICT") {
                      setActionError(`${t.enrollment.terminalConflictTitle}. ${t.enrollment.terminalConflictBody}`);
                      setTerminalAccountUncertain(false);
                    } else if (err.code === "TERMINAL_ACCOUNT_UNCONFIRMED") {
                      setActionError(`${t.enrollment.terminalUnconfirmedTitle}. ${t.enrollment.terminalUnconfirmedBody}`);
                      setTerminalAccountUncertain(true);
                    } else if (err.code === "DEVICE_COMMAND_TIMEOUT") {
                      setActionError(t.enrollment.terminalUnconfirmedBody);
                      setTerminalAccountUncertain(true);
                    } else if (err.code === "DEVICE_COMMAND_IN_PROGRESS") {
                      setActionError(t.enrollment.terminalInProgressBody);
                      setTerminalAccountUncertain(true);
                    } else if (
                      err.code === "DEVICE_UNAVAILABLE" ||
                      err.code === "COLLECTOR_UNAVAILABLE" ||
                      err.code === "DEVICE_COMMAND_QUEUE_FULL" ||
                      err.code === "DEVICE_OWNER_TIMEOUT" ||
                      err.code === "DEVICE_COMMAND_CANCELLED"
                    ) {
                      // PromptID-014 (single-owner device I/O): all of these
                      // codes mean no device write was ever attempted for
                      // this request — the Collector's connection wasn't
                      // usable, its command queue was full, the single
                      // device owner never reached a safe point to service
                      // this command in time, or it was cancelled due to a
                      // reconnect. Distinct from the unconfirmed-after-write
                      // case, which implies a device-side operation happened.
                      setActionError(`${t.enrollment.terminalUnavailableTitle}. ${t.enrollment.terminalUnavailableBody}`);
                      setTerminalAccountUncertain(false);
                    } else if (err.code === "WRITE_SESSION_EXPIRED") {
                      setActionError(t.enrollment.writeSessionExpiredMidWorkflow);
                    } else if (err.code === "WRITE_SESSION_REQUIRED" || err.code === "WRITE_DISABLED") {
                      setActionError(t.enrollment.writeSessionLockedBody);
                    } else if (err.code === "ENROLLMENT_CONFLICT") {
                      // Never surface the raw transition-engine string (e.g.
                      // "invalid enrollment transition CANCELLED -> CANCELLED")
                      // to the operator — always a friendly, localized message.
                      setActionError(
                        err.message.includes("-> CANCELLED") || err.message.includes("CANCELLED ->")
                          ? t.enrollment.alreadyCancelledBody
                          : err.message.includes("no matching attendance scan found")
                          ? t.enrollment.scanNotFoundYetBody
                          : t.enrollment.enrollmentConflictBody
                      );
                    } else {
                      setActionError(`${err.code}: ${err.message}`);
                    }
                  } else if (err instanceof ApiClientError && err.code === "WRITE_SESSION_EXPIRED") {
                    setActionError(t.enrollment.writeSessionExpiredMidWorkflow);
                  } else if (err instanceof ApiClientError && (err.code === "WRITE_SESSION_REQUIRED" || err.code === "WRITE_DISABLED")) {
                    setActionError(t.enrollment.writeSessionLockedBody);
                  } else if (err instanceof ApiClientError && err.code === "ENROLLMENT_CONFLICT") {
                    // Same friendly mapping as above, for every other action
                    // (cancel included) — the exact case reported in Bug B.
                    // Also covers confirm-controlled-scan's "no matching
                    // attendance scan found yet" (ADMS-ControlledScan-
                    // EvidenceBinding-018) with its own plain-language copy.
                    setActionError(
                      err.message.includes("-> CANCELLED") || err.message.includes("CANCELLED ->")
                        ? t.enrollment.alreadyCancelledBody
                        : err.message.includes("no matching attendance scan found")
                        ? t.enrollment.scanNotFoundYetBody
                        : t.enrollment.enrollmentConflictBody
                    );
                  } else if (err instanceof ApiClientError) {
                    setActionError(`${err.code}: ${err.message}`);
                  } else {
                    setActionError(err instanceof Error ? err.message : String(err));
                  }
                  if (action === "create-terminal-account" || action === "cancel") {
                    // Outcome may be uncertain, or the frontend's cached state
                    // may simply be stale (Bug B) — refresh from the server so
                    // the UI reflects ground truth rather than a frozen view.
                    list.reload();
                    nextActions.reload();
                  }
                } finally {
                  setBusyAction(null);
                }
              }}
            />
          ) : (
            <div className="flex h-64 flex-col items-center justify-center rounded-lg border border-slate-200 bg-white p-6 text-center text-xs text-slate-500">
              <div className="font-semibold text-slate-700">{t.enrollment.noActiveSessions}</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ReserveCard({
  operatorName,
  canMutate,
  onReserved,
}: {
  operatorName: string;
  canMutate: boolean;
  onReserved: (newId: number) => void;
}) {
  const { t } = useTranslation();
  const eligible = useApi((s) => api.humans({ production_scope: true, limit: 200 }, s), []);
  const devices = useApi((s) => api.devices(s), []);
  const [employeeId, setEmployeeId] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [operator, setOperator] = useState(operatorName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (devices.data?.items && devices.data.items.length > 0 && !deviceId) {
      setDeviceId(String(devices.data.items[0].device_id));
    }
  }, [devices.data, deviceId]);

  useEffect(() => {
    if (operatorName && !operator) {
      setOperator(operatorName);
    }
  }, [operatorName, operator]);

  function submit() {
    if (!employeeId || !deviceId || !operator.trim()) {
      setError(t.enrollment.selectPersonDeviceOperatorRequired);
      return;
    }
    setBusy(true);
    setError(null);
    api
      .reserveEnrollment({ employee_id: employeeId, device_id: Number(deviceId), operator: operator.trim() })
      .then((res) => {
        setEmployeeId("");
        onReserved(res.enrollment_id);
      })
      .catch((e: unknown) => {
        if (e instanceof ApiClientError && (e.code === "WRITE_DISABLED" || e.code === "WRITE_SESSION_REQUIRED")) {
          setError(t.enrollment.writeSessionLockedBody);
        } else if (e instanceof ApiClientError && e.code === "WRITE_SESSION_EXPIRED") {
          setError(t.enrollment.writeSessionExpiredMidWorkflow);
        } else if (
          e instanceof ApiClientError &&
          e.code === "ENROLLMENT_CONFLICT" &&
          e.message.toLowerCase().includes("already has an active enrollment")
        ) {
          // ADMS-CurrentState-History-UXClosure-022 Phase F: never show the
          // raw "ENROLLMENT_CONFLICT: Human <UUID> already has an active
          // enrollment on device <N>" text to an operator.
          setError(t.enrollment.activeEnrollmentExistsBody);
        } else if (e instanceof ApiClientError) {
          setError(`${e.code}: ${e.message}`);
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => setBusy(false));
  }

  return (
    <div className="rounded-lg border border-blue-200 bg-blue-50/30 p-4 shadow-2xs">
      <div className="flex items-center justify-between border-b border-blue-100 pb-3">
        <div className="flex items-center gap-2">
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-blue-600 font-mono text-[11px] font-bold text-white">
            1
          </span>
          <h2 className="text-sm font-bold text-slate-900">{t.enrollment.step1Title}</h2>
        </div>
        <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-700">
          Browser Action
        </span>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-4 md:items-end">
        <div>
          <label className="block text-[11px] font-bold text-slate-700">
            {t.enrollment.selectPerson} ({eligible.data?.total ?? "..."})
          </label>
          <select
            value={employeeId}
            disabled={!canMutate || busy}
            onChange={(e) => setEmployeeId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">— {t.enrollment.selectPerson} —</option>
            {eligible.data?.items.map((h) => (
              <option key={h.employee_id} value={h.employee_id}>
                {h.display_name} {h.rank ? `(${h.rank})` : ""}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-[11px] font-bold text-slate-700">{t.enrollment.selectDevice}</label>
          <select
            value={deviceId}
            disabled={!canMutate || busy}
            onChange={(e) => setDeviceId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100 disabled:text-slate-500"
          >
            {devices.data?.items.map((d) => (
              <option key={d.device_id} value={d.device_id}>
                {d.device_name} ({d.device_ip})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-[11px] font-bold text-slate-700">{t.audit.operatorColumn}</label>
          <input
            type="text"
            value={operator}
            disabled={!canMutate || busy}
            onChange={(e) => setOperator(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100 disabled:text-slate-500"
          />
        </div>

        <div>
          <button
            onClick={submit}
            disabled={!canMutate || busy || !employeeId}
            className="w-full rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-600 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-600"
          >
            {busy ? t.common.saving : t.enrollment.step1Button}
          </button>
        </div>
      </div>

      {!canMutate && (
        <div className="mt-2 text-[11px] text-amber-800">
          {t.enrollment.writeSessionLockedBody}
        </div>
      )}

      {error && <div className="mt-2 text-xs font-semibold text-rose-700">{error}</div>}
    </div>
  );
}

function ActiveEnrollmentInspector({
  enrollment,
  steps,
  canMutate,
  busyAction,
  onRunAction,
  terminalAccountUncertain,
}: {
  enrollment: Enrollment;
  steps: { id: string; label: string }[];
  canMutate: boolean;
  busyAction: string | null;
  onRunAction: (action: string, payload: Record<string, unknown>) => Promise<void>;
  terminalAccountUncertain: boolean;
}) {
  const { t } = useTranslation();
  const currentStep = getStepIndex(enrollment.status);
  // Prefer the canonical terminal-safe English name, prefixed with the
  // canonical rank abbreviation when it fits (ADMS-OperatorUX-Fingerprint-
  // Rank-Mapping-016) — never the Thai display name, which would always
  // fail the ASCII guard and forces operators to hand-type an ad hoc
  // transliteration every time.
  const namePreview = computeTerminalNamePreview(enrollment.english_name, enrollment.rank_metadata);
  const [displayName, setDisplayName] = useState(namePreview.value);
  // Tracks whether the operator has hand-edited the field during the
  // current enrollment selection — used to decide whether a canonical
  // refetch (e.g. english_name updated in Personnel) is allowed to
  // overwrite it. Reset whenever the selected enrollment changes.
  const [displayNameTouched, setDisplayNameTouched] = useState(false);
  const [lastSyncedEnrollmentId, setLastSyncedEnrollmentId] = useState(enrollment.enrollment_id);

  // Deterministic sync, not a mount-only default: whenever the selected
  // enrollment changes, always reset from its canonical english_name
  // (PromptID-012 Bug A — this component is not remounted on selection
  // change, so a useState initializer alone goes stale). While the same
  // enrollment stays selected, a canonical refetch (list/detail reload)
  // is only allowed to overwrite the field if the operator hasn't
  // touched it yet — an active manual edit is never clobbered.
  if (enrollment.enrollment_id !== lastSyncedEnrollmentId) {
    setLastSyncedEnrollmentId(enrollment.enrollment_id);
    setDisplayNameTouched(false);
    setDisplayName(namePreview.value);
  } else if (!displayNameTouched && displayName !== namePreview.value) {
    setDisplayName(namePreview.value);
  }

  const [cancelNotes, setCancelNotes] = useState("");
  const [cancelError, setCancelError] = useState(false);
  const [showCancel, setShowCancel] = useState(false);

  const { status: streamStatus, lastEvent, reconnect } = useAttendanceStream();
  // Display-only feedback that a scan arrived — never sent to the server
  // and never determines which attendance evidence gets bound (that's
  // resolved server-side, deterministically, by confirm-controlled-scan
  // itself — see ADMS-ControlledScan-EvidenceBinding-018).
  const [detectedScan, setDetectedScan] = useState<string | null>(null);

  useEffect(() => {
    if (
      lastEvent &&
      lastEvent.event_type === "ATTENDANCE_SCAN" &&
      String(lastEvent.user_id) === String(enrollment.reserved_device_user_id)
    ) {
      setDetectedScan(lastEvent.scan_time);
    }
  }, [lastEvent, enrollment.reserved_device_user_id]);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-2xs space-y-5">
      {/* Inspector Top Info */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-900">
              Session #{enrollment.enrollment_id}: {enrollment.employee_name ?? enrollment.employee_id}
            </h2>
            <StatusBadge status={enrollment.status} />
          </div>
          <div className="mt-0.5 text-xs text-slate-500">
            Target Terminal: <strong>{enrollment.device_name ?? `#${enrollment.device_id}`}</strong> · Reserved ID:{" "}
            <span className="font-mono font-bold text-blue-600">{enrollment.reserved_device_user_id}</span>
          </div>
        </div>

        {canMutate && enrollment.status !== "RETIRED" && enrollment.status !== "CANCELLED" && (
          <button
            onClick={() => setShowCancel(!showCancel)}
            className="text-xs font-semibold text-rose-600 hover:underline"
          >
            {showCancel ? t.common.close : t.enrollment.cancelSession}
          </button>
        )}
      </div>

      {/* Stepper Progress Bar */}
      <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
        <div className="grid grid-cols-6 gap-1 text-center">
          {steps.map((s, idx) => {
            const isCompleted = currentStep > idx;
            const isCurrent = currentStep === idx;
            return (
              <div key={s.id} className="flex flex-col items-center">
                <div
                  className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-bold transition-all ${
                    isCompleted
                      ? "bg-emerald-600 text-white"
                      : isCurrent
                      ? "bg-blue-600 text-white ring-2 ring-blue-300"
                      : "bg-slate-200 text-slate-600"
                  }`}
                >
                  {isCompleted ? "✓" : idx + 1}
                </div>
                <div
                  className={`mt-1 text-[10px] font-semibold leading-tight ${
                    isCurrent ? "text-blue-700 font-bold" : isCompleted ? "text-emerald-700" : "text-slate-400"
                  }`}
                >
                  {s.label}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Cancellation Drawer */}
      {showCancel && (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-xs space-y-2">
          <div className="font-bold text-rose-900">{t.enrollment.cancelSession}</div>
          <input
            type="text"
            placeholder={t.enrollment.cancelReasonPlaceholder}
            value={cancelNotes}
            onChange={(e) => {
              setCancelNotes(e.target.value);
              if (cancelError) setCancelError(false);
            }}
            className={`w-full rounded-md border bg-white px-2.5 py-1.5 text-xs text-slate-900 ${
              cancelError ? "border-rose-500 ring-1 ring-rose-300" : "border-rose-300"
            }`}
          />
          {cancelError && (
            <div className="text-[11px] font-semibold text-rose-700">{t.enrollment.cancelReasonRequired}</div>
          )}
          <button
            onClick={() => {
              if (!cancelNotes.trim()) {
                setCancelError(true);
                return;
              }
              onRunAction("cancel", { notes: cancelNotes.trim() });
            }}
            disabled={!canMutate || busyAction === "cancel"}
            className="rounded-md bg-rose-600 px-3 py-1 font-bold text-white hover:bg-rose-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busyAction === "cancel" ? t.common.saving : t.common.confirm}
          </button>
        </div>
      )}

      {/* Dynamic Action Panes */}
      {enrollment.status === "RESERVED" && (
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-blue-900">{t.enrollment.step2Title}</span>
            <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-800">
              Browser Action
            </span>
          </div>
          <p className="text-xs text-blue-900/90 leading-relaxed">
            {t.enrollment.step2Desc}
          </p>

          <div className="flex flex-wrap items-end gap-3 pt-1">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-[11px] font-bold text-blue-950">{t.enrollment.terminalDisplayName}</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => {
                  setDisplayNameTouched(true);
                  setDisplayName(e.target.value);
                }}
                disabled={!canMutate || busyAction === "create-terminal-account"}
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:ring-1 focus:ring-blue-600"
              />
              {!enrollment.english_name && (
                <p className="mt-1 text-[11px] text-blue-800/80 leading-snug">{t.enrollment.terminalNameNoEnglishHint}</p>
              )}
              {namePreview.rankOmittedForLength && (
                <p className="mt-1 text-[11px] text-blue-800/80 leading-snug">{t.enrollment.terminalNameRankOmittedHint}</p>
              )}
            </div>
            <button
              onClick={() => onRunAction("create-terminal-account", { display_name: displayName.trim() })}
              disabled={!canMutate || busyAction === "create-terminal-account" || !displayName.trim()}
              className="rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {busyAction === "create-terminal-account"
                ? t.enrollment.creatingOrVerifying
                : terminalAccountUncertain
                ? t.enrollment.verifyReconcileButton
                : t.enrollment.step2Button}
            </button>
          </div>
        </div>
      )}

      {(enrollment.status === "TERMINAL_ACCOUNT_CREATED" || enrollment.status === "FINGERPRINT_ENROLLMENT_PENDING") && (
        <div className="space-y-4">
          <div className="rounded-lg border border-indigo-200 bg-indigo-50/70 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-indigo-950">{t.enrollment.step3Title}</span>
              <span className="rounded bg-indigo-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-indigo-900">
                Physical Action at ZEM560
              </span>
            </div>
            <ol className="list-inside list-decimal space-y-1.5 text-xs text-indigo-950 leading-relaxed">
              <li>พาบุคคลไปยังเครื่องสแกน <strong>ADMS-ZEM560 (192.168.1.201)</strong></li>
              <li>กดปุ่ม <strong>Menu</strong> → เลือก <strong>User Mgt</strong> → <strong>Manage</strong></li>
              <li>ค้นหา User ID <strong className="font-mono text-indigo-950">{enrollment.reserved_device_user_id}</strong> และกด OK</li>
              <li>เลือก <strong>Enroll FP</strong> แล้ววางนิ้ว <strong>3 ครั้ง</strong> จนกว่าเครื่องจะแจ้งสำเร็จ</li>
              <li>กดปุ่ม ESC เพื่อกลับสู่หน้าจอหลัก</li>
            </ol>
          </div>

          <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 p-3.5">
            <div>
              <div className="text-xs font-bold text-slate-900">{t.enrollment.step3Title}</div>
              <div className="text-[11px] text-slate-500">{t.enrollment.step3Desc}</div>
            </div>
            <button
              onClick={() => onRunAction("confirm-fingerprint", {})}
              disabled={!canMutate || busyAction === "confirm-fingerprint"}
              className="rounded-md bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {busyAction === "confirm-fingerprint" ? t.common.saving : t.enrollment.step3Button}
            </button>
          </div>
        </div>
      )}

      {enrollment.status === "FINGERPRINT_ENROLLED" && (
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-blue-900">{t.enrollment.step4Title}</span>
            <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-800">
              Browser Action
            </span>
          </div>
          <p className="text-xs text-blue-900/90 leading-relaxed">
            {t.enrollment.step4Desc}
          </p>
          <button
            onClick={() => onRunAction("start-controlled-scan", {})}
            disabled={!canMutate || busyAction === "start-controlled-scan"}
            className="rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busyAction === "start-controlled-scan" ? t.common.saving : t.enrollment.startScanWindowButton}
          </button>
        </div>
      )}

      {enrollment.status === "CONTROLLED_SCAN_PENDING" && (
        <div className="space-y-4">
          <div className="rounded-lg border border-indigo-200 bg-indigo-50/70 p-4 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-indigo-950">{t.enrollment.step4Title}</span>
              <span className="rounded bg-indigo-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-indigo-900">
                Physical Action at ZEM560
              </span>
            </div>
            <p className="text-xs text-indigo-950 leading-relaxed">
              ให้ <strong>{enrollment.employee_name}</strong> ทำการทดสอบสแกนนิ้วที่เครื่อง ADMS-ZEM560 ทันที
            </p>
          </div>

          <div className="flex items-center justify-between">
            <StreamStatusBadge status={streamStatus} onRetry={reconnect} />
          </div>

          {/* ADMS-ControlledScan-EvidenceBinding-018: no manual/estimated
              scan-time input anywhere — the server resolves and binds the
              real attendance evidence itself when the button below is
              clicked. detectedScan (SSE) is display-only feedback that a
              scan arrived; it is never sent to the server and never
              determines what evidence gets bound. */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3">
            {detectedScan ? (
              <div className="flex items-center gap-2 text-xs text-emerald-900">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-600" />
                <span>
                  <strong>{t.enrollment.liveScanDetected}</strong> {new Date(detectedScan).toLocaleTimeString()}
                </span>
              </div>
            ) : (
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <span className="h-2.5 w-2.5 rounded-full bg-slate-300 animate-pulse" />
                <span>{t.enrollment.waitingForScan}</span>
              </div>
            )}
            <button
              onClick={() => onRunAction("confirm-controlled-scan", {})}
              disabled={!canMutate || busyAction === "confirm-controlled-scan"}
              className="rounded-md bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {busyAction === "confirm-controlled-scan" ? t.common.saving : t.enrollment.step4Button}
            </button>
          </div>
        </div>
      )}

      {enrollment.status === "CONTROLLED_SCAN_CONFIRMED" && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-950">{t.enrollment.step5Title}</span>
          </div>
          <ul className="space-y-1 text-xs text-emerald-900">
            <li className="flex items-center gap-1.5">
              <span className="text-emerald-600">✓</span> {t.enrollment.step5ChecklistTerminalAccount}
            </li>
            <li className="flex items-center gap-1.5">
              <span className="text-emerald-600">✓</span> {t.enrollment.step5ChecklistFingerprint}
            </li>
            <li className="flex items-center gap-1.5">
              <span className="text-emerald-600">✓</span> {t.enrollment.step5ChecklistScan}
            </li>
          </ul>
          <p className="text-xs font-semibold text-emerald-900 leading-relaxed">
            {t.enrollment.step5Desc}
          </p>
          <button
            onClick={() => onRunAction("mark-ready-for-mapping", {})}
            disabled={!canMutate || busyAction === "mark-ready-for-mapping"}
            className="rounded-md bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busyAction === "mark-ready-for-mapping" ? t.common.saving : t.enrollment.step5Button}
          </button>
        </div>
      )}

      {enrollment.status === "READY_FOR_MAPPING" && (
        <div className="rounded-lg border border-purple-200 bg-purple-50/80 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-purple-950">{t.enrollment.step6Title}</span>
            <span className="rounded bg-purple-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-purple-800">
              Admin Action
            </span>
          </div>
          <p className="text-xs text-purple-900 leading-relaxed">
            {t.enrollment.step6Desc}
          </p>
          <Link
            to="/mappings"
            className="inline-flex items-center gap-1.5 rounded-md bg-purple-700 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-purple-800"
          >
            {t.nav.mappings} →
          </Link>
        </div>
      )}

      {enrollment.status === "RETIRED" && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-900">
          <strong>{t.enrollment.completedTitle}:</strong> {t.enrollment.completedDesc}
        </div>
      )}

      {/* Enrollment Metadata Table */}
      <div className="border-t border-slate-100 pt-3">
        <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
          {t.enrollment.metadataInspector}
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs md:grid-cols-3">
          <MetaItem dt="Employee ID" dd={enrollment.employee_id} mono />
          <MetaItem dt="Terminal UID" dd={enrollment.device_uid ? String(enrollment.device_uid) : "—"} mono />
          <MetaItem dt="Reserved At" dd={enrollment.reserved_at ? new Date(enrollment.reserved_at).toLocaleString() : "—"} />
          <MetaItem dt="Account Created" dd={enrollment.terminal_created_at ? new Date(enrollment.terminal_created_at).toLocaleString() : "—"} />
          <MetaItem dt="FP Confirmed At" dd={enrollment.fingerprint_confirmed_at ? new Date(enrollment.fingerprint_confirmed_at).toLocaleString() : "—"} />
          <MetaItem dt="Scan Confirmed At" dd={enrollment.controlled_scan_time ? new Date(enrollment.controlled_scan_time).toLocaleString() : "—"} />
        </dl>
      </div>
    </div>
  );
}

function MetaItem({ dt, dd, mono }: { dt: string; dd: string; mono?: boolean }) {
  return (
    <div className="py-1">
      <dt className="text-[10px] font-bold uppercase text-slate-400">{dt}</dt>
      <dd className={`truncate text-slate-800 ${mono ? "font-mono text-[11px]" : ""}`}>{dd}</dd>
    </div>
  );
}
