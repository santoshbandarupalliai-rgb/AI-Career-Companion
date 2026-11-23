import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { api, setAuthLostHandler, tokenStore } from "../api/client.js";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  // On load, restore the session if tokens exist (the client refreshes them if needed).
  useEffect(() => {
    let cancelled = false;
    setAuthLostHandler(() => setUser(null));
    (async () => {
      if (!tokenStore.access && !tokenStore.refresh) {
        setLoading(false);
        return;
      }
      try {
        const { data } = await api.get("/auth/me");
        if (!cancelled) setUser(data);
      } catch {
        tokenStore.clear();
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email, password) => {
    const { data } = await api.post("/auth/login", { email, password });
    tokenStore.set(data);
    setUser(data.user);
    return data.user;
  }, []);

  const register = useCallback(async (full_name, email, password) => {
    const { data } = await api.post("/auth/register", { full_name, email, password });
    tokenStore.set(data);
    setUser(data.user);
    return data.user;
  }, []);

  const logout = useCallback(async () => {
    const refresh_token = tokenStore.refresh;
    tokenStore.clear();
    setUser(null);
    if (refresh_token) {
      try {
        await api.post("/auth/logout", { refresh_token });
      } catch {
        /* already logged out locally */
      }
    }
  }, []);

  const value = useMemo(() => ({ user, loading, login, register, logout }), [user, loading, login, register, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
