import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, getToken } from "./api/client";
import type { MeResponse, WriteSessionStatus } from "./api/types";

interface AuthState {
  me: MeResponse | null;
  loading: boolean;
  canWrite: boolean;
  serverWriteEnabled: boolean;
  writeSession: WriteSessionStatus | null;
  writeSessionActive: boolean;
  canMutate: boolean;
  isAdmin: boolean;
  reload: () => void;
}

const AuthContext = createContext<AuthState>({
  me: null,
  loading: true,
  canWrite: false,
  serverWriteEnabled: false,
  writeSession: null,
  writeSessionActive: false,
  canMutate: false,
  isAdmin: false,
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
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!getToken()) {
      setMe(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .me()
      .then(setMe)
      .catch(() => setMe(null))
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

  return (
    <AuthContext.Provider
      value={{
        me,
        loading,
        canWrite,
        serverWriteEnabled,
        writeSession,
        writeSessionActive,
        canMutate,
        isAdmin: role === "ADMIN",
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
