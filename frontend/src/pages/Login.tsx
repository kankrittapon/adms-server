import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, getToken, setToken } from "../api/client";
import { useAuth } from "../auth";
import { useTranslation } from "../i18n";
import { friendlyApiError } from "../i18n/apiErrors";

export function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const { reload } = useAuth();
  const { locale, setLocale, t } = useTranslation();

  // Already authenticated -> straight in.
  if (getToken()) {
    navigate("/", { replace: true });
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.login(username.trim(), password);
      setToken(res.token);
      // Client-side navigation never remounts AuthProvider, so without this
      // the identity from the PREVIOUS session (or null, on a first login)
      // stays stuck in memory until a hard page refresh forces a remount —
      // the exact "shows the wrong role until Ctrl+Shift+R" bug.
      reload();
      navigate("/", { replace: true });
    } catch (err) {
      setError(friendlyApiError(err, t));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4 font-sans text-slate-900 antialiased">
      <div className="w-full max-w-md">
        {/* Language switch on login screen */}
        <div className="flex justify-end mb-3">
          <div className="inline-flex rounded-lg border border-slate-200 bg-white p-0.5 shadow-2xs">
            <button
              type="button"
              onClick={() => setLocale("th")}
              className={`rounded-md px-2.5 py-1 text-xs font-bold transition-all ${
                locale === "th"
                  ? "bg-blue-600 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              TH
            </button>
            <button
              type="button"
              onClick={() => setLocale("en")}
              className={`rounded-md px-2.5 py-1 text-xs font-bold transition-all ${
                locale === "en"
                  ? "bg-blue-600 text-white shadow-xs"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              EN
            </button>
          </div>
        </div>

        {/* Card Header & Brand */}
        <div className="rounded-t-xl border-x border-t border-slate-200 bg-white p-6 text-center shadow-2xs">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-xl bg-blue-600 font-mono text-lg font-bold text-white shadow-xs">
            AD
          </div>
          <h1 className="mt-3 text-lg font-bold tracking-tight text-slate-900">{t.login.title}</h1>
          <p className="text-xs text-slate-500 mt-1">{t.login.subtitle}</p>

          <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-[11px] font-semibold text-slate-600">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            {t.login.environment}: 192.168.1.248
          </div>
        </div>

        {/* Card Form Body */}
        <form
          onSubmit={submit}
          className="rounded-b-xl border border-slate-200 bg-white p-6 pt-2 shadow-sm space-y-4"
        >
          {error && (
            <div className="rounded-md border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800 flex items-start gap-2">
              <span className="font-bold text-rose-600">!</span>
              <div>{t.login.failed} ({error})</div>
            </div>
          )}

          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider" htmlFor="username">
              {t.login.usernameLabel}
            </label>
            <input
              id="username"
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              placeholder={t.login.usernamePlaceholder}
              disabled={busy}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100"
            />
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider" htmlFor="password">
              {t.login.passwordLabel}
            </label>
            <input
              id="password"
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              placeholder={t.login.passwordPlaceholder}
              disabled={busy}
              className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-xs text-slate-900 shadow-2xs focus:border-blue-600 focus:outline-none focus:ring-1 focus:ring-blue-600 disabled:bg-slate-100"
            />
          </div>

          <div className="pt-2">
            <button
              type="submit"
              disabled={busy || !username.trim() || !password}
              className="flex w-full items-center justify-center rounded-md bg-blue-600 px-4 py-2 text-xs font-bold text-white shadow-xs transition-colors hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:text-slate-500"
            >
              {busy ? (
                <span className="flex items-center gap-2">
                  <span className="h-3 w-3 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  {t.login.signingIn}
                </span>
              ) : (
                t.login.signInButton
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
