"use client";

import React, { createContext, useContext, useState, useEffect, useCallback } from "react";

const ADMIN_BASE = "http://localhost:8005";
const TOKEN_KEY = "portal_dev_token";

export interface Developer {
  developer_id: string;
  email: string;
  display_name: string;
  team_id: string | null;
  team_name: string | null;
}

interface AuthContextValue {
  developer: Developer | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, displayName: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  selectTeam: (teamId: string) => Promise<void>;
  setDeveloper: (dev: Developer) => void;
}

const AuthContext = createContext<AuthContextValue>({
  developer: null,
  token: null,
  loading: true,
  login: async () => {},
  register: async () => {},
  logout: async () => {},
  selectTeam: async () => {},
  setDeveloper: () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [developer, setDeveloper] = useState<Developer | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Restore session on mount
  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (!storedToken) { setLoading(false); return; }
    fetch(`${ADMIN_BASE}/dev-auth/me`, {
      headers: { Authorization: `Bearer ${storedToken}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then((data: Developer | null) => {
        if (data) {
          setDeveloper(data);
          setToken(storedToken);
        } else {
          localStorage.removeItem(TOKEN_KEY);
        }
      })
      .catch(() => { localStorage.removeItem(TOKEN_KEY); })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${ADMIN_BASE}/dev-auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `Login failed (${res.status})`);
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.token);
    setToken(data.token);
    setDeveloper(data);
  }, []);

  const register = useCallback(async (email: string, displayName: string, password: string) => {
    const res = await fetch(`${ADMIN_BASE}/dev-auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, display_name: displayName, password }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `Registration failed (${res.status})`);
    }
    const data = await res.json();
    localStorage.setItem(TOKEN_KEY, data.token);
    setToken(data.token);
    setDeveloper(data);
  }, []);

  const logout = useCallback(async () => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (storedToken) {
      await fetch(`${ADMIN_BASE}/dev-auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${storedToken}` },
      }).catch(() => {});
    }
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setDeveloper(null);
  }, []);

  const selectTeam = useCallback(async (teamId: string) => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (!storedToken) return;
    const res = await fetch(`${ADMIN_BASE}/dev-auth/select-team?team_id=${encodeURIComponent(teamId)}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${storedToken}` },
    });
    if (res.ok) {
      const data = await res.json();
      setDeveloper(data);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ developer, token, loading, login, register, logout, selectTeam, setDeveloper }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

// Backwards-compat shim so existing portal pages that use useTeam() still work
export function useTeam() {
  const { developer } = useAuth();
  return {
    teamId: developer?.team_id ?? null,
    teamName: developer?.team_name ?? null,
    setTeam: () => {},
  };
}
