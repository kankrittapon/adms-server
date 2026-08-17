import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, getToken } from "./api/client";
import type { MeResponse } from "./api/types";

interface AuthState {
  me: MeResponse | null;
  loading: boolean;
  canWrite: boolean;
  serverWriteEnabled: boolean;
  canMutate: boolean;
  isAdmin: boolean;
  reload: () => void;
}

const AuthContext = createContext<AuthState>({
  me: null,
  loading: true,
  canWrite: false,
  serverWriteEnabled: false,
  canMutate: false,
  isAdmin: false,
  reload: () => {},
});

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

  const role = me?.role ?? "";
  const canWrite = role === "OPERATOR" || role === "ADMIN";
  const serverWriteEnabled = me?.write_enabled ?? false;
  const canMutate = canWrite && serverWriteEnabled;

  return (
    <AuthContext.Provider
      value={{
        me,
        loading,
        canWrite,
        serverWriteEnabled,
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
