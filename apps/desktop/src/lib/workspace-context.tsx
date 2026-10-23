import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { ApiError, api, type Workspace } from "./api";
import { useAuth } from "./auth";

interface WorkspaceContextValue {
  workspaces: Workspace[];
  current: Workspace | null;
  loading: boolean;
  error: string | null;
  setCurrent: (id: string) => void;
  reload: () => Promise<void>;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);
const CURRENT_KEY = "onestats.workspace";

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentId, setCurrentId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!user) {
      setWorkspaces([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const list = await api.myWorkspaces();
      setWorkspaces(list);
      const stored = (() => {
        try {
          return localStorage.getItem(CURRENT_KEY);
        } catch {
          return null;
        }
      })();
      setCurrentId((prev) => {
        const candidate = prev ?? stored ?? null;
        return list.some((w) => w.id === candidate) ? candidate : (list[0]?.id ?? null);
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Failed to load workspaces");
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const setCurrent = useCallback((id: string) => {
    setCurrentId(id);
    try {
      localStorage.setItem(CURRENT_KEY, id);
    } catch {
      /* ignore */
    }
  }, []);

  const current = workspaces.find((w) => w.id === currentId) ?? null;

  const value = useMemo(
    () => ({ workspaces, current, loading, error, setCurrent, reload }),
    [workspaces, current, loading, error, setCurrent, reload],
  );
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("useWorkspace must be used within WorkspaceProvider");
  return ctx;
}
