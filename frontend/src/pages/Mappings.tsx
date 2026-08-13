import { useState } from "react";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { useApi } from "../hooks/useApi";
import { ErrorBanner, Loading, StatusBadge } from "../components/Status";
import type { MappingEligibilityItem } from "../api/types";

export function Mappings() {
  const { isAdmin } = useAuth();
  const { data, loading, error, reload } = useApi((s) => api.mappings({ limit: 100 }, s), []);

  return (
    <div>
      <h1 className="mb-4 text-xl font-semibold">Mapping</h1>
      {isAdmin && <CreateMappingPanel onCreated={reload} />}
      {loading ? (
        <Loading />
      ) : error ? (
        <ErrorBanner message={error} />
      ) : (
        <table className="w-full border-collapse bg-white text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="px-3 py-2">mapping_id</th>
              <th className="px-3 py-2">Human</th>
              <th className="px-3 py-2">device_user</th>
              <th className="px-3 py-2">status</th>
              <th className="px-3 py-2">valid_from</th>
              <th className="px-3 py-2">valid_to</th>
              <th className="px-3 py-2">method</th>
              <th className="px-3 py-2">verified_by</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((m) => (
              <tr key={m.mapping_id} className="border-b border-gray-100">
                <td className="px-3 py-2 font-mono text-xs">{m.mapping_id}</td>
                <td className="px-3 py-2">{m.employee_name ?? m.employee_id.slice(0, 8)}</td>
                <td className="px-3 py-2 font-mono text-xs">{m.device_user_id ?? m.device_user_pk}</td>
                <td className="px-3 py-2">
                  <StatusBadge status={m.mapping_status} />
                </td>
                <td className="px-3 py-2 font-mono text-xs">{fmt(m.valid_from)}</td>
                <td className="px-3 py-2 font-mono text-xs">{m.valid_to ? fmt(m.valid_to) : "—"}</td>
                <td className="px-3 py-2">{m.verification_method}</td>
                <td className="px-3 py-2">{m.verified_by}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function fmt(iso: string): string {
  return iso.replace("T", " ").slice(0, 19);
}

function CreateMappingPanel({ onCreated }: { onCreated: () => void }) {
  const { me } = useAuth();
  const elig = useApi((s) => api.mappingEligibility(s), []);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [verifiedBy, setVerifiedBy] = useState(me?.username ?? "");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [writeDisabled, setWriteDisabled] = useState(false);

  const item: MappingEligibilityItem | null =
    elig.data?.items.find((e) => e.enrollment_id === selectedId) ?? null;

  function submit() {
    if (!item || !verifiedBy.trim() || !note.trim()) {
      setError("Select an eligible enrollment, and fill verified_by + note.");
      return;
    }
    if (!window.confirm(
      `Create VERIFIED mapping?\n\nHuman: ${item.employee_name} (${item.employee_id})\n` +
        `Terminal account: ${item.device_user_id} (pk ${item.device_user_pk})\n` +
        `Controlled scan: ${item.controlled_scan_time ?? "—"} (attendance id ${item.controlled_attendance_id ?? "?"})\n` +
        `Enrollment #${item.enrollment_id} will be consumed (retired).`
    )) {
      return;
    }
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
        elig.reload();
        onCreated();
      })
      .catch((e: unknown) => {
        if (e instanceof ApiClientError && e.code === "WRITE_DISABLED") {
          setWriteDisabled(true);
          setError(
            "Write endpoints are disabled on the server (API_WRITE_ENABLED=false). " +
              "Enable the write flag to create mappings."
          );
        } else if (e instanceof ApiClientError) {
          setError(`${e.code}: ${e.message}`);
        } else {
          setError(e instanceof Error ? e.message : String(e));
        }
      })
      .finally(() => setBusy(false));
  }

  return (
    <div className="mb-6 rounded border border-gray-200 bg-white p-4">
      <h2 className="mb-3 text-base font-semibold">Create VERIFIED mapping (admin)</h2>
      <p className="mb-3 max-w-3xl text-sm text-gray-500">
        Choose a <code>READY_FOR_MAPPING</code> enrollment with completed controlled-scan
        evidence. Creating the mapping consumes (retires) the enrollment. This is the only
        path to a VERIFIED temporal identity — no automatic matching ever.
      </p>
      {writeDisabled && (
        <div className="mb-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
          <strong>Writes disabled.</strong> <code>API_WRITE_ENABLED=false</code> — enable for a
          real mapping session.
        </div>
      )}
      {error && <ErrorBanner message={error} />}
      {elig.loading ? (
        <Loading />
      ) : elig.error ? (
        <ErrorBanner message={elig.error} />
      ) : elig.data?.items.length === 0 ? (
        <p className="text-sm text-gray-500">
          No eligible enrollments — no <code>READY_FOR_MAPPING</code> enrollment without an
          existing VERIFIED mapping.
        </p>
      ) : (
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col text-xs text-gray-500">
            Enrollment (READY_FOR_MAPPING)
            <select
              value={selectedId ?? ""}
              onChange={(e) => {
                setSelectedId(e.target.value ? Number(e.target.value) : null);
                setError(null);
              }}
              className="mt-1 w-80 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-900"
            >
              <option value="">— select —</option>
              {elig.data?.items.map((e) => (
                <option key={e.enrollment_id} value={e.enrollment_id}>
                  #{e.enrollment_id} · {e.employee_name ?? e.employee_id.slice(0, 8)} · terminal {e.reserved_device_user_id}
                </option>
              ))}
            </select>
          </label>
          {item && (
            <div className="rounded border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-900">
              <div>
                Human: <strong>{item.employee_name}</strong> · terminal{" "}
                <strong>{item.device_user_id}</strong> (pk {item.device_user_pk})
              </div>
              <div>
                Controlled scan: {item.controlled_scan_time ? fmt(item.controlled_scan_time) : "—"} ·
                attendance id <strong>{item.controlled_attendance_id ?? "?"}</strong>
              </div>
              <div>Confirmed by: {item.confirmed_by ?? "—"} · device: {item.device_name}</div>
            </div>
          )}
          <label className="flex flex-col text-xs text-gray-500">
            Verified by
            <input
              type="text"
              value={verifiedBy}
              onChange={(e) => setVerifiedBy(e.target.value)}
              className="mt-1 w-44 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-900"
            />
          </label>
          <label className="flex flex-col text-xs text-gray-500">
            Verification note
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="audit note referencing evidence"
              className="mt-1 w-72 rounded border border-gray-300 px-2 py-1.5 text-sm text-gray-900"
            />
          </label>
          <button
            onClick={submit}
            disabled={busy}
            className="rounded bg-blue-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
          >
            {busy ? "Creating…" : "Create VERIFIED mapping"}
          </button>
        </div>
      )}
    </div>
  );
}
