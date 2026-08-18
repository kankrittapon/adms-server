import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, getToken } from "./api/client";
import type { MeResponse, WriteSessionStatus } from "./api/types";

interface AuthState {
  me: MeResponse | null;
  loading: boolean;
  authError: boolean;
  canWrite: boolean;
  serverWriteEnabled: boolean;
  writeSession: WriteSessionStatus | null;
  writeSessionActive: boolean;
  canMutate: boolean;
  isAdmin: boolean;
  // ADMS-RBAC-OperationalRoles-023: canonical frontend capability helpers —
  // never scatter raw `role === "..."` comparisons across pages. These are
  // UX-only (hide irrelevant controls for elderly/non-technical operators);
  // the backend's require_roles() dependencies on each endpoint remain the
  // sole source of truth. Keep this list in sync with app/api/auth.py's
  // ROLES_* sets — it deliberately mirrors them, not reinvents them.
  canOpenWorkSession: boolean;
  canEnroll: boolean;
  canVerifyIdentity: boolean;
  canManagePersonnel: boolean;
  canManageTerminal: boolean;
  canManageOperators: boolean;
  reload: () => void;
}

const AuthContext = createContext<AuthState>({
  me: null,
  loading: true,
  authError: false,
  canWrite: false,
  serverWriteEnabled: false,
  writeSession: null,
  writeSessionActive: false,
  canMutate: false,
  isAdmin: false,
  canOpenWorkSession: false,
  canEnroll: false,
  canVerifyIdentity: false,
  canManagePersonnel: false,
  canManageTerminal: false,
  canManageOperators: false,
  reload: () => {},
});

// Roles permitted to mutate domain data (matches ROLES_ENROLLMENT_MUTATE /
// ROLES_ADMIN_ONLY on the backend — app/api/auth.py). ENROLLMENT_OPERATOR
// was previously missing here, which silently disabled its own enrollment
// buttons client-side even though the backend already allowed the role to
// act (a UX bug, not a security hole — the backend was always the real
// authorization boundary).
const WRITE_CAPABLE_ROLES = new Set(["ENROLLMENT_OPERATOR", "OPERATOR", "ADMIN"]);

// While a write session is active, poll /auth/me periodically so the
// remaining-time countdown shown in the UI stays live without a websocket.
const WRITE_SESSION_POLL_MS = 30_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [authError, setAuthError] = useState(false);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!getToken()) {
      setMe(null);
      setAuthError(false);
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .me()
      .then((res) => {
        setMe(res);
        setAuthError(false);
      })
      .catch(() => {
        // Never silently downgrade an auth failure into "VIEWER" — me stays
        // null (unknown identity) and authError tells the UI to show an
        // explicit session-error state with a re-login action, distinct
        // from the brief "still loading" window.
        setMe(null);
        setAuthError(true);
      })
      .finally(() => setLoading(false));
  }, [tick]);

  const writeSession = me?.write_session ?? null;
  const writeSessionActive = writeSession?.active ?? false;

  useEffect(() => {
    if (!getToken() || !writeSessionActive) return;
    const interval = setInterval(() => {
      api.me().then(setMe).catch(() => {});
    }, WRITE_SESSION_POLL_MS);
    return () => clearInterval(interval);
  }, [writeSessionActive]);

  const role = me?.role ?? "";
  const canWrite = WRITE_CAPABLE_ROLES.has(role);
  const serverWriteEnabled = me?.write_enabled ?? false;
  const canMutate = canWrite && serverWriteEnabled && writeSessionActive;
  const isAdmin = role === "ADMIN";
  const isOperatorOrAdmin = role === "OPERATOR" || role === "ADMIN";

  return (
    <AuthContext.Provider
      value={{
        me,
        loading,
        authError,
        canWrite,
        serverWriteEnabled,
        writeSession,
        writeSessionActive,
        canMutate,
        isAdmin,
        // Mirrors app/api/auth.py's ROLES_OPERATOR_PLUS — matches the
        // write-session router's actual gate (Phase 3).
        canOpenWorkSession: isOperatorOrAdmin,
        // Mirrors ROLES_ENROLLMENT_MUTATE.
        canEnroll: canWrite,
        // Separation of duties (Phase 9): final identity/mapping
        // verification, Personnel admin lifecycle, destructive Terminal
        // Management, and operator/role management all remain ADMIN-only
        // — confirmed by source audit of every corresponding router
        // (mappings.py, humans.py, terminal_management.py, operators.py),
        // not assumed.
        canVerifyIdentity: isAdmin,
        canManagePersonnel: isAdmin,
        canManageTerminal: isAdmin,
        canManageOperators: isAdmin,
        reload: () => setTick((t) => t + 1),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
