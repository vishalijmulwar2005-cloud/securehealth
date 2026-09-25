"use client";
/** Auth context: server-backed identity only. Demo role switching is never a
 * production authentication model (AppFlow §3). Session restores via the
 * selected refresh flow once; failure clears protected state (UI/UX §7). */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, tokens } from "./api";
import type { Role, User } from "./types";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (body: { email: string; password: string; full_name: string; role: Role; specialty?: string }) => Promise<User>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  login: async () => { throw new Error("unmounted"); },
  register: async () => { throw new Error("unmounted"); },
  logout: async () => {},
});

export const roleHome: Record<string, string> = {
  PATIENT: "/patient",
  DOCTOR: "/doctor",
  SYSTEM_ADMIN: "/admin",
  HOSPITAL_ADMIN: "/admin",
  REGULATOR: "/regulator",
};

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        if (tokens.access || tokens.refresh) {
          setUser(await api.get<User>("/auth/me"));
        }
      } catch {
        setUser(null);
        tokens.clear();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.post<{ user: User; access_token: string; refresh_token: string }>(
      "/auth/login", { email, password });
    tokens.set(data.access_token, data.refresh_token);
    const me = await api.get<User>("/auth/me");
    setUser(me);
    return me;
  }, []);

  const register = useCallback(async (body: { email: string; password: string; full_name: string; role: Role; specialty?: string }) => {
    const data = await api.post<{ user: User; access_token: string; refresh_token: string }>(
      "/auth/register", body);
    tokens.set(data.access_token, data.refresh_token);
    const me = await api.get<User>("/auth/me");
    setUser(me);
    return me;
  }, []);

  const logout = useCallback(async () => {
    const refresh = tokens.refresh;
    try {
      if (refresh) await api.post("/auth/logout", { refresh_token: refresh });
    } finally {
      tokens.clear();
      setUser(null);
    }
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout }),
    [user, loading, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
