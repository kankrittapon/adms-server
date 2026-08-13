import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { api, getToken } from "./api/client";
import type { MeResponse } from "./api/client";

interface AuthState {
  me: MeResponse | null;
  loading: boolean;
  canWrite: boolean;
  isAdmin: boolean;
  reload: () => void;
}

const AuthContext = createContext<AuthState>({
  me: null,
  loading: true,
  canWrite: false,
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

  return (
    <AuthContext.Provider
      value={{ me, loading, canWrite, isAdmin: role === "ADMIN", reload: () => setTick((t) => t + 1) }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  return useContext(AuthContext);
}
