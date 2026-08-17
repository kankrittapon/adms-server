import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { useApi } from "../hooks/useApi";
import { useAttendanceStream } from "../hooks/useAttendanceStream";
import { ErrorBanner, Loading, StatusBadge, WriteGateStatusBadge } from "../components/Status";
import type { Enrollment, EnrollmentNextActions } from "../api/types";

const STEPS = [
  { id: "RESERVED", label: "1. Reserved", desc: "Terminal ID allocated" },
  { id: "TERMINAL_ACCOUNT_CREATED", label: "2. Terminal Account", desc: "Account on device" },
  { id: "FINGERPRINT_ENROLLED", label: "3. Fingerprint", desc: "Biometric captured" },
  { id: "CONTROLLED_SCAN_CONFIRMED", label: "4. Controlled Scan", desc: "Attendance verified" },
  { id: "READY_FOR_MAPPING", label: "5. Ready for Mapping", desc: "Ready for admin" },
  { id: "RETIRED", label: "6. Verified Mapping", desc: "Active mapping" },
];

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
  const { me, canWrite, serverWriteEnabled, canMutate } = useAuth();
  const list = useApi((s) => api.enrollments({ limit: 100 }, s), []);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  // Auto-select the first or newest enrollment if none selected
  useEffect(() => {
    if (selectedId === null && list.data?.items && list.data.items.length > 0) {
      setSelectedId(list.data.items[0].enrollment_id);
    }
  }, [list.data, selectedId]);

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
          <h1 className="text-xl font-bold tracking-tight text-slate-900">Enrollment Workspace</h1>
          <p className="text-xs text-slate-500">
            Guided operator workflow to safely allocate terminal IDs, create terminal accounts, verify biometrics, and produce verified attendance mappings.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <WriteGateStatusBadge writeEnabled={serverWriteEnabled} />
        </div>
      </div>

      {/* Proactive Write Gate Banner */}
      {!serverWriteEnabled && (
        <div className="flex items-start gap-3 rounded-lg border border-amber-300 bg-amber-50 p-3.5 text-xs text-amber-900 shadow-2xs">
          <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-200 font-bold text-amber-900">
            !
          </div>
          <div>
            <div className="font-bold">Production Writes Locked (Safe Mode)</div>
            <div className="mt-0.5 text-amber-800 leading-relaxed">
              The ADMS server is operating in safety read-only mode (<code>API_WRITE_ENABLED=false</code>). All mutation controls (Reservation, Terminal Account Creation, State Confirmations) are viewable below but disabled until an administrator enables server writes.
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
        canWrite={canWrite}
        serverWriteEnabled={serverWriteEnabled}
        onReserved={(newId) => {
          setActionError(null);
          setActionSuccess("Enrollment reserved successfully. Proceed to Step 2 below.");
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
              Enrollment Sessions ({list.data?.total ?? 0})
            </h2>
            <button
              onClick={() => list.reload()}
              className="text-[11px] font-medium text-blue-600 hover:underline"
            >
              Refresh queue
            </button>
          </div>

          {list.loading ? (
            <Loading />
          ) : list.error ? (
            <ErrorBanner message={list.error} />
          ) : (list.data?.items.length ?? 0) === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white p-8 text-center text-xs text-slate-500">
              No enrollment sessions recorded. Use the form above to reserve the first terminal ID.
            </div>
          ) : (
            <div className="space-y-2">
              {list.data?.items.map((e) => {
                const isSelected = selectedId === e.enrollment_id;
                const stepIdx = getStepIndex(e.status);
                return (
                  <div
                    key={e.enrollment_id}
                    onClick={() => {
                      setSelectedId(e.enrollment_id);
                      setActionError(null);
                      setActionSuccess(null);
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
                        {stepIdx >= 0 ? `Step ${stepIdx + 1} of 6` : "Cancelled"}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Right Col: Active Enrollment Inspector & Guided Stepper (7 cols) */}
        <div className="lg:col-span-7">
          {selected ? (
            <ActiveEnrollmentInspector
              enrollment={selected}
              canMutate={canMutate}
              busyAction={busyAction}
              onRunAction={async (action, payload) => {
                setBusyAction(action);
                setActionError(null);
                setActionSuccess(null);
                try {
                  if (action === "create-terminal-account") {
                    await api.createTerminalAccount(
                      selected.enrollment_id,
                      payload.display_name as string,
                      me?.username ?? "operator"
                    );
                    setActionSuccess("Terminal account created on device. Take the person to ZEM560 to enroll fingerprint.");
                  } else if (action === "start-fingerprint-enrollment") {
                    await api.startFingerprintEnrollment(selected.enrollment_id, me?.username ?? "operator");
                    setActionSuccess("Fingerprint enrollment window active.");
                  } else if (action === "confirm-fingerprint") {
                    await api.confirmFingerprintEnrolled(selected.enrollment_id, me?.username ?? "operator");
                    setActionSuccess("Fingerprint confirmed. Proceed to controlled scan.");
                  } else if (action === "start-controlled-scan") {
                    await api.startControlledScan(selected.enrollment_id, me?.username ?? "operator");
                    setActionSuccess("Controlled scan window started (5 minutes). Ask person to scan finger now.");
                  } else if (action === "confirm-controlled-scan") {
                    await api.confirmControlledScan(selected.enrollment_id, me?.username ?? "operator", payload.scan_time as string);
                    setActionSuccess("Controlled scan confirmed. Ready for mapping.");
                  } else if (action === "mark-ready-for-mapping") {
                    await api.markReadyForMapping(selected.enrollment_id, me?.username ?? "operator");
                    setActionSuccess("Marked READY_FOR_MAPPING. An Admin can now activate the mapping.");
                  } else if (action === "cancel") {
                    await api.cancelEnrollment(selected.enrollment_id, me?.username ?? "operator", payload.notes as string);
                    setActionSuccess("Enrollment cancelled.");
                  }
                  list.reload();
                  nextActions.reload();
                } catch (err: unknown) {
                  if (err instanceof ApiClientError) {
                    setActionError(`${err.code}: ${err.message}`);
                  } else {
                    setActionError(err instanceof Error ? err.message : String(err));
                  }
                } finally {
                  setBusyAction(null);
                }
              }}
            />
          ) : (
            <div className="flex h-64 flex-col items-center justify-center rounded-lg border border-slate-200 bg-white p-6 text-center text-xs text-slate-500">
              <div className="font-semibold text-slate-700">No Enrollment Selected</div>
              <div className="mt-1">Select an enrollment session from the left queue to view and drive its workflow.</div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Step 1: Start New Enrollment (Reserve) Card
// ---------------------------------------------------------------------------
function ReserveCard({
  operatorName,
  canMutate,
  canWrite,
  serverWriteEnabled,
  onReserved,
}: {
  operatorName: string;
  canMutate: boolean;
  canWrite: boolean;
  serverWriteEnabled: boolean;
  onReserved: (newId: number) => void;
}) {
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
      setError("Please select a Human, a Device, and enter the operator name.");
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
        if (e instanceof ApiClientError && e.code === "WRITE_DISABLED") {
          setError("Server writes are locked (API_WRITE_ENABLED=false).");
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
          <h2 className="text-sm font-bold text-slate-900">Step 1: Start New Enrollment (Reserve Terminal ID)</h2>
        </div>
        <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-700">
          Browser Action
        </span>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-4 md:items-end">
        <div>
          <label className="block text-[11px] font-bold text-slate-700">
            Human (Production Scope: {eligible.data?.total ?? "..."})
          </label>
          <select
            value={employeeId}
            disabled={!canMutate || busy}
            onChange={(e) => setEmployeeId(e.target.value)}
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100 disabled:text-slate-500"
          >
            <option value="">— Select Personnel —</option>
            {eligible.data?.items.map((h) => (
              <option key={h.employee_id} value={h.employee_id}>
                {h.display_name} {h.rank ? `(${h.rank})` : ""}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-[11px] font-bold text-slate-700">Target Terminal Device</label>
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
          <label className="block text-[11px] font-bold text-slate-700">Operator</label>
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
            {busy ? "Reserving..." : "Reserve Terminal ID"}
          </button>
        </div>
      </div>

      {!canWrite ? (
        <div className="mt-2 text-[11px] text-slate-500">
          ℹ️ Logged in as <strong>VIEWER</strong>. Reservation requires OPERATOR or ADMIN role.
        </div>
      ) : !serverWriteEnabled ? (
        <div className="mt-2 text-[11px] text-amber-800">
          🔒 Reservation disabled: Server writes are locked (<code>API_WRITE_ENABLED=false</code>).
        </div>
      ) : null}

      {error && <div className="mt-2 text-xs font-semibold text-rose-700">{error}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Active Enrollment Inspector with Stepper & Step Guidance
// ---------------------------------------------------------------------------
function ActiveEnrollmentInspector({
  enrollment,
  canMutate,
  busyAction,
  onRunAction,
}: {
  enrollment: Enrollment;
  canMutate: boolean;
  busyAction: string | null;
  onRunAction: (action: string, payload: Record<string, unknown>) => Promise<void>;
}) {
  const currentStep = getStepIndex(enrollment.status);
  const [displayName, setDisplayName] = useState(enrollment.employee_name ?? "");
  const [scanTime, setScanTime] = useState("");
  const [cancelNotes, setCancelNotes] = useState("");
  const [showCancel, setShowCancel] = useState(false);

  // SSE Stream for Realtime Attendance Scan Detection
  const { lastEvent } = useAttendanceStream();
  const [detectedScan, setDetectedScan] = useState<string | null>(null);

  useEffect(() => {
    if (
      lastEvent &&
      lastEvent.event_type === "ATTENDANCE_SCAN" &&
      String(lastEvent.user_id) === String(enrollment.reserved_device_user_id)
    ) {
      setDetectedScan(lastEvent.scan_time);
      setScanTime(new Date(lastEvent.scan_time).toISOString().slice(0, 16));
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
            {showCancel ? "Close cancel" : "Cancel session"}
          </button>
        )}
      </div>

      {/* Stepper Progress Bar */}
      <div className="rounded-lg bg-slate-50 p-3 border border-slate-100">
        <div className="grid grid-cols-6 gap-1 text-center">
          {STEPS.map((s, idx) => {
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

      {/* Cancellation Drawer if active */}
      {showCancel && (
        <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-xs space-y-2">
          <div className="font-bold text-rose-900">Cancel Enrollment Session</div>
          <input
            type="text"
            placeholder="Cancellation reason (required)"
            value={cancelNotes}
            onChange={(e) => setCancelNotes(e.target.value)}
            className="w-full rounded-md border border-rose-300 bg-white px-2.5 py-1.5 text-xs text-slate-900"
          />
          <button
            onClick={() => {
              if (!cancelNotes.trim()) return alert("Enter a cancellation reason.");
              onRunAction("cancel", { notes: cancelNotes.trim() });
            }}
            className="rounded-md bg-rose-600 px-3 py-1 font-bold text-white hover:bg-rose-700"
          >
            Confirm Cancellation
          </button>
        </div>
      )}

      {/* Dynamic Action & Guidance Panes based on State */}
      {enrollment.status === "RESERVED" && (
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-blue-900">Step 2: Create Terminal Account on Device</span>
            <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-800">
              Browser Action
            </span>
          </div>
          <p className="text-xs text-blue-900/90 leading-relaxed">
            Writes the reserved terminal ID <strong className="font-mono text-blue-950">{enrollment.reserved_device_user_id}</strong> to the physical terminal <strong>ADMS-ZEM560</strong> with NORMAL user privilege. This establishes the terminal record without requiring terminal menu access or SSH.
          </p>

          <div className="flex flex-wrap items-end gap-3 pt-1">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-[11px] font-bold text-blue-950">Terminal Display Name (ASCII)</label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                disabled={!canMutate || busyAction === "create-terminal-account"}
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:ring-1 focus:ring-blue-600"
              />
            </div>
            <button
              onClick={() => onRunAction("create-terminal-account", { display_name: displayName.trim() || enrollment.employee_name })}
              disabled={!canMutate || busyAction === "create-terminal-account" || !displayName.trim()}
              className="rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {busyAction === "create-terminal-account" ? "Writing to terminal..." : "Create Terminal Account on Device"}
            </button>
          </div>
        </div>
      )}

      {(enrollment.status === "TERMINAL_ACCOUNT_CREATED" || enrollment.status === "FINGERPRINT_ENROLLMENT_PENDING") && (
        <div className="space-y-4">
          {/* Physical Terminal Instruction Banner */}
          <div className="rounded-lg border border-indigo-200 bg-indigo-50/70 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-indigo-950">Step 3: Physical Fingerprint Enrollment at Terminal</span>
              <span className="rounded bg-indigo-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-indigo-900">
                Physical Action at ZEM560
              </span>
            </div>
            <ol className="list-inside list-decimal space-y-1.5 text-xs text-indigo-950 leading-relaxed">
              <li>Take the person to terminal <strong>ADMS-ZEM560 (192.168.1.201)</strong>.</li>
              <li>Press <strong>Menu</strong> → select <strong>User Mgt</strong> → <strong>Manage</strong>.</li>
              <li>Find User ID <strong className="font-mono text-indigo-950">{enrollment.reserved_device_user_id}</strong> and press OK.</li>
              <li>Select <strong>Enroll FP</strong> and guide the person to place their finger on the sensor <strong>3 times</strong> until accepted.</li>
              <li>Press ESC to return to the home screen.</li>
            </ol>
          </div>

          {/* Web Confirmation Action */}
          <div className="flex items-center justify-between rounded-lg border border-slate-200 bg-slate-50 p-3.5">
            <div>
              <div className="text-xs font-bold text-slate-900">Confirm Biometric Template Enrolled</div>
              <div className="text-[11px] text-slate-500">Click once the fingerprint is successfully enrolled at the physical terminal.</div>
            </div>
            <button
              onClick={() => onRunAction("confirm-fingerprint", {})}
              disabled={!canMutate || busyAction === "confirm-fingerprint"}
              className="rounded-md bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {busyAction === "confirm-fingerprint" ? "Confirming..." : "Confirm Fingerprint Enrolled"}
            </button>
          </div>
        </div>
      )}

      {enrollment.status === "FINGERPRINT_ENROLLED" && (
        <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-blue-900">Step 4a: Initiate Controlled Scan Window</span>
            <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-blue-800">
              Browser Action
            </span>
          </div>
          <p className="text-xs text-blue-900/90 leading-relaxed">
            Opens a 5-minute controlled scan window. During this window, the person will scan their newly enrolled finger to verify that the attendance logging engine captures their scan.
          </p>
          <button
            onClick={() => onRunAction("start-controlled-scan", {})}
            disabled={!canMutate || busyAction === "start-controlled-scan"}
            className="rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busyAction === "start-controlled-scan" ? "Starting..." : "Start 5-Minute Controlled Scan Window"}
          </button>
        </div>
      )}

      {enrollment.status === "CONTROLLED_SCAN_PENDING" && (
        <div className="space-y-4">
          {/* Physical Scan Instruction */}
          <div className="rounded-lg border border-indigo-200 bg-indigo-50/70 p-4 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-indigo-950">Step 4b: Person Scans Finger on Terminal</span>
              <span className="rounded bg-indigo-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-indigo-900">
                Physical Action at ZEM560
              </span>
            </div>
            <p className="text-xs text-indigo-950 leading-relaxed">
              Ask <strong>{enrollment.employee_name}</strong> to place their finger on the ADMS-ZEM560 terminal sensor right now. The live attendance engine will detect the event automatically.
            </p>
            {enrollment.controlled_scan_window_until && (
              <div className="text-[11px] font-mono text-indigo-900 font-semibold">
                Window expires at: {new Date(enrollment.controlled_scan_window_until).toLocaleTimeString()}
              </div>
            )}
          </div>

          {/* Realtime Scan Detection Alert */}
          {detectedScan && (
            <div className="flex items-center justify-between rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-xs text-emerald-900 animate-pulse">
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full bg-emerald-600" />
                <span>
                  <strong>Realtime Scan Detected!</strong> Terminal ID <strong>{enrollment.reserved_device_user_id}</strong> scanned at <code className="font-mono">{detectedScan}</code>.
                </span>
              </div>
              <span className="rounded bg-emerald-200 px-2 py-0.5 font-mono text-[10px] font-bold text-emerald-900">
                AUTO-CAPTURED
              </span>
            </div>
          )}

          {/* Controlled Scan Confirmation Form */}
          <div className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-900">Step 4c: Submit Controlled Scan Confirmation</span>
              <span className="rounded bg-slate-200 px-2 py-0.5 text-[10px] font-bold uppercase text-slate-700">
                Web Confirmation
              </span>
            </div>
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex-1 min-w-[200px]">
                <label className="block text-[11px] font-bold text-slate-700">Scan Timestamp (Local / ISO)</label>
                <input
                  type="datetime-local"
                  value={scanTime}
                  onChange={(e) => setScanTime(e.target.value)}
                  disabled={!canMutate || busyAction === "confirm-controlled-scan"}
                  className="mt-1 w-full rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:ring-1 focus:ring-blue-600"
                />
              </div>
              <button
                onClick={() => {
                  if (!scanTime) return alert("Select or enter the scan timestamp.");
                  onRunAction("confirm-controlled-scan", { scan_time: new Date(scanTime).toISOString() });
                }}
                disabled={!canMutate || busyAction === "confirm-controlled-scan" || !scanTime}
                className="rounded-md bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
              >
                {busyAction === "confirm-controlled-scan" ? "Submitting..." : "Confirm Controlled Scan"}
              </button>
            </div>
          </div>
        </div>
      )}

      {enrollment.status === "CONTROLLED_SCAN_CONFIRMED" && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50/70 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-950">Step 5: Mark Ready for Mapping</span>
            <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-800">
              Web Action
            </span>
          </div>
          <p className="text-xs text-emerald-900 leading-relaxed">
            Controlled scan evidence is confirmed. Advance this enrollment to <code>READY_FOR_MAPPING</code> so an Administrator can review and activate the final VERIFIED temporal mapping.
          </p>
          <button
            onClick={() => onRunAction("mark-ready-for-mapping", {})}
            disabled={!canMutate || busyAction === "mark-ready-for-mapping"}
            className="rounded-md bg-emerald-600 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-slate-300"
          >
            {busyAction === "mark-ready-for-mapping" ? "Advancing..." : "Mark Ready for Mapping"}
          </button>
        </div>
      )}

      {enrollment.status === "READY_FOR_MAPPING" && (
        <div className="rounded-lg border border-purple-200 bg-purple-50/80 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-purple-950">Step 6: Ready for Admin Mapping Verification</span>
            <span className="rounded bg-purple-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-purple-800">
              Admin Action
            </span>
          </div>
          <p className="text-xs text-purple-900 leading-relaxed">
            This enrollment has completed all physical biometric and scan steps. It is now queued for an Administrator to verify and activate as a permanent temporal identity mapping.
          </p>
          <Link
            to="/mappings"
            className="inline-flex items-center gap-1.5 rounded-md bg-purple-700 px-4 py-2 text-xs font-bold text-white shadow-xs hover:bg-purple-800"
          >
            Go to Mapping Management →
          </Link>
        </div>
      )}

      {enrollment.status === "RETIRED" && (
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-900">
          <strong>Mapping Completed:</strong> This enrollment session was consumed to create an active VERIFIED identity mapping.
        </div>
      )}

      {/* Enrollment Metadata Table */}
      <div className="border-t border-slate-100 pt-3">
        <div className="mb-2 text-[10px] font-bold uppercase tracking-wider text-slate-400">
          Session Technical Audit Data
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
