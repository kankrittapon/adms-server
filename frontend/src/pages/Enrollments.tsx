import { useState } from "react";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatusBadge } from "../components/Status";
import type { Enrollment, EnrollmentNextActions, Human, Device } from "../api/types";

const ACTION_LABELS: Record<string, string> = {
  "start-fingerprint-enrollment": "Start fingerprint enrollment",
  "confirm-fingerprint": "Confirm fingerprint enrolled",
  "start-controlled-scan": "Start controlled scan window",
  "confirm-controlled-scan": "Confirm controlled scan",
  "mark-ready-for-mapping": "Mark ready for mapping",
  cancel: "Cancel enrollment",
};

export function Enrollments() {
  const { me, canWrite } = useAuth();
  const list = useApi((s) => api.enrollments({ limit: 100 }, s), []);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [writeDisabled, setWriteDisabled] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [scanInput, setScanInput] = useState(false);
  const [cancelInput, setCancelInput] = useState(false);
  const [scanValue, setScanValue] = useState("");
  const [cancelReason, setCancelReason] = useState("");

  const selected: Enrollment | null =
    list.data?.items.find((e) => e.enrollment_id === selectedId) ?? null;

  const nextActions = useApi<EnrollmentNextActions | null>(
    (s) => (selectedId ? api.enrollmentNextActions(selectedId, s) : Promise.resolve(null)),
    [selectedId]
  );

  async function runAction(action: string, payload: Record<string, unknown>) {
    if (!selectedId || !me) return;
    setBusy(action);
    setActionError(null);
    try {
      switch (action) {
        case "start-fingerprint-enrollment":
          await api.startFingerprintEnrollment(selectedId, me.username);
          break;
        case "confirm-fingerprint":
          await api.confirmFingerprintEnrolled(selectedId, me.username);
          break;
        case "start-controlled-scan":
          await api.startControlledScan(selectedId, me.username);
          break;
        case "confirm-controlled-scan":
          await api.confirmControlledScan(selectedId, me.username, payload.scan_time as string);
          break;
        case "mark-ready-for-mapping":
          await api.markReadyForMapping(selectedId, me.username);
          break;
        case "cancel":
          await api.cancelEnrollment(selectedId, me.username, payload.notes as string);
          break;
      }
      setScanInput(false);
      setCancelInput(false);
      setScanValue("");
      setCancelReason("");
      list.reload();
      nextActions.reload();
    } catch (e) {
      if (e instanceof ApiClientError && e.code === "WRITE_DISABLED") {
        setWriteDisabled(true);
        setActionError(
          "Write endpoints are disabled on the server (API_WRITE_ENABLED=false). " +
            "Enable the write flag for real operator usage before driving the workflow."
        );
      } else if (e instanceof ApiClientError) {
        setActionError(`${e.code}: ${e.message}`);
      } else {
        setActionError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(null);
    }
  }

  function confirmThen(action: string, label: string) {
    if (window.confirm(`${label} — proceed?`)) {
      void runAction(action, {});
    }
  }

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Enrollment workflow</h1>
      <p className="mb-4 max-w-3xl text-sm text-gray-500">
        Controlled enrollment operator workflow: reserve a production terminal ID, then drive the
        state machine through fingerprint confirmation, controlled scan, and ready-for-mapping.
        Actions are role-gated (operator/admin) and require the server write flag to be enabled.
      </p>

      {writeDisabled && (
        <div className="mb-4 rounded border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          <strong>Writes disabled.</strong> The API is running with <code>API_WRITE_ENABLED=false</code> —
          read-only until the operator enables it for a real enrollment session.
        </div>
      )}
      {actionError && <ErrorBanner message={actionError} />}

      {canWrite && (
        <ReserveForm
          operatorName={me?.username ?? ""}
          onReserved={() => {
            setActionError(null);
            list.reload();
          }}
        />
      )}

      <div className="mt-6">
        {list.loading ? (
          <Loading />
        ) : list.error ? (
          <ErrorBanner message={list.error} />
        ) : (
          <table className="w-full border-collapse bg-white text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="px-3 py-2">id</th>
                <th className="px-3 py-2">Human</th>
                <th className="px-3 py-2">terminal id</th>
                <th className="px-3 py-2">status</th>
                <th className="px-3 py-2">reserved_by</th>
                <th className="px-3 py-2">controlled scan</th>
                <th className="px-3 py-2">confirmed_by</th>
              </tr>
            </thead>
            <tbody>
              {list.data?.items.map((e) => (
                <tr
                  key={e.enrollment_id}
                  onClick={() => {
                    setSelectedId(e.enrollment_id);
                    setActionError(null);
                    setWriteDisabled(false);
                    setScanInput(false);
                    setCancelInput(false);
                  }}
                  className={`cursor-pointer border-b border-gray-100 ${
                    selectedId === e.enrollment_id ? "bg-blue-50" : "hover:bg-gray-50"
                  }`}
                >
                  <td className="px-3 py-2 font-mono text-xs">{e.enrollment_id}</td>
                  <td className="px-3 py-2">{e.employee_name ?? e.employee_id.slice(0, 8)}</td>
                  <td className="px-3 py-2 font-mono text-xs">{e.reserved_device_user_id}</td>
                  <td className="px-3 py-2">
                    <StatusBadge status={e.status} />
                  </td>
                  <td className="px-3 py-2">{e.reserved_by}</td>
                  <td className="px-3 py-2 font-mono text-xs">{e.controlled_scan_time ?? "—"}</td>
                  <td className="px-3 py-2">{e.confirmed_by ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selected && (
        <div className="mt-6 rounded border border-gray-200 bg-white p-4">
          <h2 className="mb-3 text-base font-semibold">
            Enrollment #{selected.enrollment_id} <StatusBadge status={selected.status} />
          </h2>
          <dl className="mb-4 grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-3">
            <Info dt="Human" dd={selected.employee_name ?? selected.employee_id} />
            <Info dt="Device" dd={selected.device_name ?? `#${selected.device_id}`} />
            <Info dt="Reserved terminal ID" dd={selected.reserved_device_user_id} />
            <Info dt="Reserved by" dd={selected.reserved_by ?? "—"} />
            <Info dt="Reserved at" dd={selected.reserved_at ?? "—"} />
            <Info dt="Fingerprint confirmed" dd={selected.fingerprint_confirmed_at ?? "—"} />
            <Info dt="Scan window until" dd={selected.controlled_scan_window_until ?? "—"} />
            <Info dt="Scan time" dd={selected.controlled_scan_time ?? "—"} />
            <Info dt="Confirmed by" dd={selected.confirmed_by ?? "—"} />
            <Info dt="Notes" dd={selected.notes ?? "—"} />
          </dl>

          {!canWrite ? (
            <p className="text-sm text-gray-500">
              Viewer role — read-only. An operator or admin can drive this workflow.
            </p>
          ) : writeDisabled ? (
            <p className="text-sm text-gray-500">Write actions are disabled on the server.</p>
          ) : nextActions.loading ? (
            <Loading />
          ) : nextActions.error ? (
            <ErrorBanner message={nextActions.error} />
          ) : (nextActions.data?.next_actions.length ?? 0) === 0 ? (
            <p className="text-sm text-gray-500">
              No further operator actions in state <code>{selected.status}</code>.
              {selected.status === "READY_FOR_MAPPING" && " Awaiting admin VERIFIED mapping creation."}
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              {nextActions.data?.next_actions.map((a) => {
                if (busy === a.action) {
                  return (
                    <span key={a.action} className="rounded bg-gray-100 px-3 py-1.5 text-sm text-gray-500">
                      Working…
                    </span>
                  );
                }
                if (a.action === "confirm-controlled-scan") {
                  return scanInput ? (
                    <span key={a.action} className="flex items-center gap-2">
                      <input
                        type="datetime-local"
                        value={scanValue}
                        onChange={(e) => setScanValue(e.target.value)}
                        className="rounded border border-gray-300 px-2 py-1 text-sm"
                      />
                      <button
                        onClick={() =>
                          scanValue
                            ? void runAction(a.action, { scan_time: new Date(scanValue).toISOString() })
                            : window.alert("Enter the controlled scan time first.")
                        }
                        className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
                      >
                        Submit scan time
                      </button>
                    </span>
                  ) : (
                    <button
                      key={a.action}
                      onClick={() => setScanInput(true)}
                      className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
                    >
                      {ACTION_LABELS[a.action]}
                    </button>
                  );
                }
                if (a.action === "cancel") {
                  return cancelInput ? (
                    <span key={a.action} className="flex items-center gap-2">
                      <input
                        type="text"
                        placeholder="Cancellation reason (required)"
                        value={cancelReason}
                        onChange={(e) => setCancelReason(e.target.value)}
                        className="w-64 rounded border border-gray-300 px-2 py-1 text-sm"
                      />
                      <button
                        onClick={() =>
                          cancelReason.trim()
                            ? void runAction(a.action, { notes: cancelReason.trim() })
                            : window.alert("A cancellation reason is required.")
                        }
                        className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
                      >
                        Confirm cancel
                      </button>
                    </span>
                  ) : (
                    <button
                      key={a.action}
                      onClick={() => setCancelInput(true)}
                      className="rounded border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50"
                    >
                      {ACTION_LABELS[a.action]}
                    </button>
                  );
                }
                return (
                  <button
                    key={a.action}
                    onClick={() => confirmThen(a.action, ACTION_LABELS[a.action] ?? a.action)}
                    className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
                  >
                    {ACTION_LABELS[a.action] ?? a.action}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ReserveForm({ operatorName, onReserved }: { operatorName: string; onReserved: () => void }) {
  const eligible = useApi<PageOf<Human>>((s) => api.humans({ production_scope: true, limit: 200 }, s), []);
  const devices = useApi<PageOf<Device>>((s) => api.devices(s), []);
  const [employeeId, setEmployeeId] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [operator, setOperator] = useState(operatorName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function submit() {
    if (!employeeId || !deviceId || !operator.trim()) {
      setError("Human, device, and operator are required.");
      return;
    }
    setBusy(true);
    setError(null);
    api
      .reserveEnrollment({ employee_id: employeeId, device_id: Number(deviceId), operator: operator.trim() })
      .then(() => {
        setEmployeeId("");
        onReserved();
      })
      .catch((e: unknown) => {
        if (e instanceof ApiClientError && e.code === "WRITE_DISABLED") {
          setError("Write endpoints are disabled on the server (API_WRITE_ENABLED=false).");
        } else if (e instanceof ApiClientError) {
          setError(`${e.code}: ${e.message}`);
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => setBusy(false));
  }

  return (
    <div className="rounded border border-gray-200 bg-white p-4">
      <h2 className="mb-3 text-base font-semibold">Reserve production terminal ID</h2>
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col text-xs text-gray-500">
          Human (production scope)
          <select
            value={employeeId}
            onChange={(e) => setEmployeeId(e.target.value)}
            className="mt-1 w-72 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-900"
          >
            <option value="">— select —</option>
            {eligible.data?.items.map((h) => (
              <option key={h.employee_id} value={h.employee_id}>
                {h.display_name} {h.rank ? `(${h.rank})` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-xs text-gray-500">
          Device
          <select
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
            className="mt-1 w-52 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-900"
          >
            <option value="">— select —</option>
            {devices.data?.items.map((d) => (
              <option key={d.device_id} value={d.device_id}>
                {d.device_name} ({d.device_ip})
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col text-xs text-gray-500">
          Operator
          <input
            type="text"
            value={operator}
            onChange={(e) => setOperator(e.target.value)}
            className="mt-1 w-44 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-900"
          />
        </label>
        <button
          onClick={submit}
          disabled={busy}
          className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? "Reserving…" : "Reserve"}
        </button>
      </div>
      {error && <div className="mt-2 text-sm text-red-600">{error}</div>}
    </div>
  );
}

type PageOf<T> = { items: T[]; total: number; limit: number; offset: number };

function Info({ dt, dd }: { dt: string; dd: string }) {
  return (
    <div className="py-0.5">
      <dt className="text-xs uppercase tracking-wide text-gray-500">{dt}</dt>
      <dd className="break-words">{dd}</dd>
    </div>
  );
}
