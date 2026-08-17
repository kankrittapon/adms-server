import { useState } from "react";
import { api, ApiClientError } from "../api/client";
import { useAuth } from "../auth";
import { Badge, ErrorBanner, Loading, StatCard } from "../components/Status";
import { WriteSessionControl } from "../components/WriteSessionControl";
import { useApi } from "../hooks/useApi";
import { useTranslation } from "../i18n";

export function System() {
  const { me } = useAuth();
  const { t } = useTranslation();
  const health = useApi((s) => api.health(s), []);
  const ranks = useApi((s) => api.ranks(s), []);

  const isAdmin = me?.role === "ADMIN";

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="border-b border-slate-200 pb-4">
        <h1 className="text-xl font-bold tracking-tight text-slate-900">{t.system.title}</h1>
        <p className="text-xs text-slate-500">{t.system.subtitle}</p>
      </div>

      {/* Runtime Write Session control (ADMIN opens/closes; every role sees status) */}
      <WriteSessionControl />

      {/* System Telemetry Cards */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-5">
        {health.loading ? (
          <div className="col-span-full">
            <Loading />
          </div>
        ) : health.error ? (
          <div className="col-span-full">
            <ErrorBanner message={health.error} />
          </div>
        ) : health.data ? (
          <>
            {/* A successful response to this request already proves the Web
                API is reachable — no separate backend field needed. */}
            <StatCard
              label={t.system.apiService}
              value={
                <Badge tone="green">{t.system.apiReachable}</Badge>
              }
            />
            <StatCard
              label={t.system.databaseService}
              value={
                <Badge tone={health.data.database === "HEALTHY" ? "green" : "red"}>
                  {health.data.database === "HEALTHY" ? t.status.dbHealthy : t.status.dbDegraded}
                </Badge>
              }
            />
            <StatCard
              label={t.system.mqttService}
              value={
                <Badge tone={health.data.mqtt === "HEALTHY" ? "green" : "amber"}>
                  {health.data.mqtt === "HEALTHY" ? t.status.mqttHealthy : (health.data.mqtt ?? "—")}
                </Badge>
              }
              hint={t.system.mqttHint}
            />
            <StatCard
              label={t.system.collectorService}
              value={health.data.collector?.state === "LIVE" ? t.status.collectorLive : (health.data.collector?.state ?? "—")}
              hint={health.data.collector?.device_connected ? t.status.deviceConnected : t.status.deviceDisconnected}
              tone={health.data.collector?.device_connected ? "highlight" : "normal"}
            />
            <StatCard
              label={t.system.lastUpdatedLabel}
              value={health.data.timestamp ? new Date(health.data.timestamp).toLocaleTimeString() : "—"}
              hint={health.data.timestamp ? new Date(health.data.timestamp).toLocaleDateString() : ""}
            />
          </>
        ) : null}
      </div>

      {/* Operator Security Section */}
      <ChangePasswordForm />

      {/* Operator Accounts Management Panel (Admin Only) */}
      {isAdmin && <OperatorAccountsManagement />}

      {/* RTN Rank Reference Table */}
      <div className="space-y-3 pt-2">
        <div className="flex items-center justify-between border-b border-slate-200 pb-2">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            {t.system.rankReferenceTitle} ({ranks.data?.length ?? 0})
          </h2>
          <span className="text-[11px] text-slate-400">Canonical Display Metadata</span>
        </div>

        {ranks.loading ? (
          <Loading />
        ) : ranks.error ? (
          <ErrorBanner message={ranks.error} />
        ) : (
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-2xs">
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-left text-xs table-dense">
                <thead>
                  <tr>
                    <th>Thai Full Rank</th>
                    <th>Thai Abbreviation</th>
                    <th>English Rank</th>
                    <th>English Abbr</th>
                    <th>Rank Category</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {ranks.data?.map((r) => (
                    <tr key={r.rank_th_abbreviation} className="transition-colors hover:bg-slate-50/80">
                      <td className="font-semibold text-slate-900">{r.rank_th_full}</td>
                      <td>
                        <span className="font-mono text-slate-700 bg-slate-100 px-1.5 py-0.5 rounded text-[11px]">
                          {r.rank_th_abbreviation}
                        </span>
                      </td>
                      <td className="text-slate-800">{r.rank_en}</td>
                      <td className="font-mono text-slate-600 text-[11px]">{r.rank_en_abbreviation}</td>
                      <td>
                        <span className="inline-block rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] text-slate-700">
                          {r.rank_category}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function ChangePasswordForm() {
  const { t } = useTranslation();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!current || next.length < 12) {
      setMsg({ tone: "err", text: "Enter your current password and a new password of at least 12 characters." });
      return;
    }
    setBusy(true);
    setMsg(null);
    api
      .changePassword(current, next)
      .then((r) => {
        setCurrent("");
        setNext("");
        setMsg({
          tone: "ok",
          text: `${t.system.passwordChangedSuccess} (${r.other_tokens_revoked} other session(s) revoked)`,
        });
      })
      .catch((e: unknown) => {
        if (e instanceof ApiClientError) {
          setMsg({ tone: "err", text: `${e.code}: ${e.message}` });
        } else {
          setMsg({ tone: "err", text: e instanceof Error ? e.message : String(e) });
        }
      })
      .finally(() => setBusy(false));
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
      <div className="border-b border-slate-100 pb-3">
        <h2 className="text-sm font-bold text-slate-900">{t.system.changePasswordTitle}</h2>
        <p className="mt-0.5 text-xs text-slate-500">
          Changing your password signs out all other active sessions (this current session stays authenticated).
        </p>
      </div>

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

      <form onSubmit={submit} className="flex flex-wrap items-end gap-3 pt-1">
        <div className="flex-1 min-w-[200px]">
          <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
            {t.system.currentPassword}
          </label>
          <input
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            disabled={busy}
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100"
          />
        </div>

        <div className="flex-1 min-w-[200px]">
          <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
            {t.system.newPassword}
          </label>
          <input
            type="password"
            value={next}
            onChange={(e) => setNext(e.target.value)}
            disabled={busy}
            className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100"
          />
        </div>

        <div>
          <button
            type="submit"
            disabled={busy || !current || next.length < 12}
            className="rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-600 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
          >
            {busy ? t.common.saving : t.system.changePasswordButton}
          </button>
        </div>
      </form>
    </div>
  );
}

function OperatorAccountsManagement() {
  const { t } = useTranslation();
  const { me } = useAuth();
  const operators = useApi((s) => api.listOperators(s), []);

  const [username, setUsername] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("ENROLLMENT_OPERATOR");
  const [createBusy, setCreateBusy] = useState(false);
  const [createMsg, setCreateMsg] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [toggleError, setToggleError] = useState<string | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !displayName.trim() || password.length < 12) {
      setCreateMsg({ tone: "err", text: "Username, Display Name, and Password (≥ 12 chars) are required." });
      return;
    }
    setCreateBusy(true);
    setCreateMsg(null);
    try {
      await api.createOperator({
        username: username.trim(),
        display_name: displayName.trim(),
        password: password,
        role: role,
      });
      setUsername("");
      setDisplayName("");
      setPassword("");
      setCreateMsg({ tone: "ok", text: `Operator account '${username}' created successfully.` });
      operators.reload();
    } catch (err) {
      setCreateMsg({ tone: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setCreateBusy(false);
    }
  }

  async function handleToggle(operatorId: number, currentActive: boolean) {
    setToggleError(null);
    try {
      await api.toggleOperatorActive(operatorId, !currentActive);
      operators.reload();
    } catch (err) {
      setToggleError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-4">
      <div className="border-b border-slate-100 pb-3 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-bold text-slate-900">{t.system.operatorsTitle}</h2>
          <p className="mt-0.5 text-xs text-slate-500">{t.system.operatorsSubtitle}</p>
        </div>
        <Badge tone="purple">ADMIN ONLY</Badge>
      </div>

      {toggleError && (
        <div className="rounded-md border border-rose-300 bg-rose-50 p-3 text-xs font-medium text-rose-900">
          {toggleError}
        </div>
      )}

      {createMsg && (
        <div
          className={`rounded-md border p-3 text-xs font-medium ${
            createMsg.tone === "ok"
              ? "border-emerald-300 bg-emerald-50 text-emerald-900"
              : "border-rose-300 bg-rose-50 text-rose-900"
          }`}
        >
          {createMsg.text}
        </div>
      )}

      {/* Create Operator Form */}
      <form onSubmit={handleCreate} className="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3">
        <div className="text-xs font-bold text-slate-800">{t.system.createOperatorButton}</div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
              {t.system.username}
            </label>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. enroll_staff"
              disabled={createBusy}
              className="mt-1 w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            />
          </div>
          <div>
            <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
              {t.system.displayName}
            </label>
            <input
              type="text"
              required
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="e.g. Staff Name"
              disabled={createBusy}
              className="mt-1 w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            />
          </div>
          <div>
            <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
              {t.system.role}
            </label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              disabled={createBusy}
              className="mt-1 w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            >
              <option value="ENROLLMENT_OPERATOR">{t.roles.enrollmentOperator}</option>
              <option value="VIEWER">{t.roles.viewer}</option>
              <option value="OPERATOR">{t.roles.operator}</option>
              <option value="ADMIN">{t.roles.admin}</option>
            </select>
            <p className="mt-1 text-[11px] leading-snug text-slate-500">
              {role === "ADMIN"
                ? t.roles.adminDesc
                : role === "OPERATOR"
                ? t.roles.operatorDesc
                : role === "ENROLLMENT_OPERATOR"
                ? t.roles.enrollmentOperatorDesc
                : t.roles.viewerDesc}
            </p>
          </div>
          <div>
            <label className="block text-[11px] font-bold text-slate-700 uppercase tracking-wider">
              {t.system.initialPassword} (≥ 12 chars)
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              disabled={createBusy}
              className="mt-1 w-full rounded border border-slate-300 bg-white px-2.5 py-1.5 text-xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600"
            />
          </div>
        </div>
        <div className="flex justify-end pt-1">
          <button
            type="submit"
            disabled={createBusy || !username.trim() || !displayName.trim() || password.length < 12}
            className="rounded bg-blue-600 px-4 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-blue-700 disabled:opacity-50"
          >
            {createBusy ? t.common.saving : t.system.createAccount}
          </button>
        </div>
      </form>

      {/* Operators List Table */}
      {operators.loading ? (
        <Loading />
      ) : operators.error ? (
        <ErrorBanner message={operators.error} />
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200">
          <table className="w-full border-collapse text-left text-xs table-dense">
            <thead>
              <tr>
                <th>{t.system.username}</th>
                <th>{t.system.displayName}</th>
                <th>{t.system.role}</th>
                <th>{t.common.status}</th>
                <th>Created</th>
                <th>{t.common.actions}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {operators.data?.map((op) => (
                <tr key={op.operator_id} className="transition-colors hover:bg-slate-50/80">
                  <td className="font-mono font-bold text-slate-900">{op.username}</td>
                  <td>{op.display_name}</td>
                  <td>
                    <span className="inline-block rounded px-2 py-0.5 text-[10px] font-bold bg-slate-100 text-slate-800 border border-slate-200">
                      {op.role}
                    </span>
                  </td>
                  <td>
                    {op.active ? (
                      <span className="inline-flex items-center gap-1 font-semibold text-emerald-700">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        {t.common.active}
                      </span>
                    ) : (
                      <span className="text-slate-400">{t.common.inactive}</span>
                    )}
                  </td>
                  <td className="text-slate-500 font-mono text-[11px]">
                    {new Date(op.created_at).toLocaleDateString()}
                  </td>
                  <td>
                    {op.operator_id === me?.operator_id ? (
                      <span className="text-slate-400 italic text-[11px]">(Current Session)</span>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleToggle(op.operator_id, op.active)}
                        className={`rounded px-2 py-0.5 text-[11px] font-semibold transition-colors border ${
                          op.active
                            ? "border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100"
                            : "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                        }`}
                      >
                        {op.active ? t.system.deactivate : t.system.activate}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
