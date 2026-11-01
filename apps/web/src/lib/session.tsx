"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api, ApiError, type Me, type Org, type Role } from "./api";

const ORG_KEY = "mla.currentOrg"; // per-viewer convenience only; the API checks membership on every call

interface SessionValue {
  me: Me | null;
  org: Org | null;
  role: Role | undefined;
  loading: boolean;
  setMe: (me: Me) => void;
  switchOrg: (id: string) => void;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

function readStoredOrg(): string | null {
  try { return localStorage.getItem(ORG_KEY); } catch { return null; }
}
function storeOrg(id: string) {
  try { localStorage.setItem(ORG_KEY, id); } catch { /* private mode: keep in memory only */ }
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMeState] = useState<Me | null>(null);
  const [orgId, setOrgId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const setMe = useCallback((value: Me) => {
    setMeState(value);
    const stored = readStoredOrg();
    const ids = value.memberships.map((m) => m.organization.id);
    setOrgId(stored && ids.includes(stored) ? stored : ids[0] ?? null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      setMe(await api<Me>("/auth/me"));
    } catch (err) {
      if (!(err instanceof ApiError && err.status === 401)) throw err;
      setMeState(null);
    } finally {
      setLoading(false);
    }
  }, [setMe]);

  useEffect(() => { refresh().catch(() => setLoading(false)); }, [refresh]);

  const switchOrg = useCallback((id: string) => { storeOrg(id); setOrgId(id); }, []);

  const logout = useCallback(async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    setMeState(null);
  }, []);

  const value = useMemo<SessionValue>(() => {
    const membership = me?.memberships.find((m) => m.organization.id === orgId);
    return { me, org: membership?.organization ?? null, role: membership?.role, loading, setMe, switchOrg, logout, refresh };
  }, [me, orgId, loading, setMe, switchOrg, logout, refresh]);

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession outside SessionProvider");
  return ctx;
}

/** Inside the app shell: an organization is guaranteed, otherwise the user is sent to login. */
export function useRequireSession() {
  const s = useSession();
  const router = useRouter();
  const path = usePathname();
  useEffect(() => {
    if (!s.loading && !s.me) router.replace(`/entrar/?voltar=${encodeURIComponent(path)}`);
  }, [s.loading, s.me, router, path]);
  return s;
}
