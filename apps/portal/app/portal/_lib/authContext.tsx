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

export interface TeamMembership {
  membership_id: string;
  role: "member" | "admin";
  joined_at: string;
  team_id: string;
  team_name: string;
  team_slug: string;
  area_name: string | null;
  area_color: string | null;
}

interface AuthContextValue {
  developer: Developer | null;
  token: string | null;
  loading: boolean;
  memberships: TeamMembership[];
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
  memberships: [],
  login: async () => {},
  register: async () => {},
  logout: async () => {},
  selectTeam: async () => {},
  setDeveloper: () => {},
});

async function fetchMemberships(developerId: string, authToken: string): Promise<TeamMembership[]> {
  try {
    const res = await fetch(`${ADMIN_BASE}/developers/${developerId}/teams`, {
      headers: { Authorization: `Bearer ${authToken}` },
    });
    if (!res.ok) return [];
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch {
    return [];
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [developer, setDeveloper] = useState<Developer | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [memberships, setMemberships] = useState<TeamMembership[]>([]);

  // Restore session on mount
  useEffect(() => {
    const storedToken = localStorage.getItem(TOKEN_KEY);
    if (!storedToken) { setLoading(false); return; }
    fetch(`${ADMIN_BASE}/dev-auth/me`, {
      headers: { Authorization: `Bearer ${storedToken}` },
    })
      .then(r => r.ok ? r.json() : null)
      .then(async (data: Developer | null) => {
        if (data) {
          setDeveloper(data);
          setToken(storedToken);
          const m = await fetchMemberships(data.developer_id, storedToken);
          setMemberships(m);
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
    const m = await fetchMemberships(data.developer_id, data.token);
    setMemberships(m);
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
    const m = await fetchMemberships(data.developer_id, data.token);
    setMemberships(m);
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
    setMemberships([]);
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
      // Memberships don't change on team switch, but refresh to stay consistent
      const m = await fetchMemberships(data.developer_id, storedToken);
      setMemberships(m);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ developer, token, loading, memberships, login, register, logout, selectTeam, setDeveloper }}>
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
