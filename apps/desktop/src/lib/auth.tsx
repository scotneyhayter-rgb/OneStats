import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, api, getToken, setToken, type User } from "./api";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  backendError: string | null;
  setupRequired: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

/** Poll the backend's health until it responds, or the deadline passes. Lets the packaged standalone
 * backend finish starting (DB wait + migrations) before the app decides it is unreachable. */
async function waitForBackend(timeoutMs = 45000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    try {
      await api.health();
      return;
    } catch {
      if (Date.now() >= deadline) return; // give up quietly; the normal flow will surface the error
      await new Promise((r) => setTimeout(r, 1000));
    }
  }
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [setupRequired, setSetupRequired] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setBackendError(null);
    try {
      // Standalone: the packaged backend sidecar may still be starting (DB wait + migrations).
      // Poll health briefly so the app shows "Starting OneStats…" instead of a backend-down error.
      await waitForBackend();
      const status = await api.setupStatus();
      setSetupRequired(status.setup_required);
      if (getToken()) {
        try {
          setUser(await api.me());
        } catch (e) {
          if (e instanceof ApiError && e.status === 401) {
            setToken(null);
            setUser(null);
          } else {
            throw e;
          }
        }
      } else {
        setUser(null);
      }
    } catch (e) {
      setBackendError(e instanceof ApiError ? e.message : "Unexpected error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login(username, password);
    setToken(res.token);
    setUser(res.user);
    setSetupRequired(false);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* ignore */
    }
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, backendError, setupRequired, login, logout, refresh }),
    [user, loading, backendError, setupRequired, login, logout, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
