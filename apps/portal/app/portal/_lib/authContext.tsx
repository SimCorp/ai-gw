"use client";

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from "react";

// TODO: migrate to HttpOnly cookie for full XSS protection (requires backend refactor)
const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";
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
  mustChangePassword: boolean;
  login: (email: string, password: string, rememberMe?: boolean) => Promise<void>;
  register: (email: string, displayName: string, password: string) => Promise<void>;
  changePassword: (newPassword: string) => Promise<void>;
  logout: () => Promise<void>;
  selectTeam: (teamId: string) => Promise<void>;
  setDeveloper: (dev: Developer) => void;
}

const AuthContext = createContext<AuthContextValue>({
  developer: null,
  token: null,
  loading: true,
  memberships: [],
  mustChangePassword: false,
  login: async () => {},
  register: async () => {},
  changePassword: async (_newPassword: string) => {},
  logout: async () => {},
  selectTeam: async () => {},
  setDeveloper: () => {},
});

function storeToken(token: string, persist: boolean) {
  if (persist) {
    localStorage.setItem(TOKEN_KEY, token);
    sessionStorage.removeItem(TOKEN_KEY);
  } else {
    sessionStorage.setItem(TOKEN_KEY, token);
    localStorage.removeItem(TOKEN_KEY);
  }
}

function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY) ?? sessionStorage.getItem(TOKEN_KEY);
}

function clearStoredToken() {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
}

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
  const [mustChangePassword, setMustChangePassword] = useState(false);

  // Stored temporarily when must_change_password=true; cleared after password change
  const pendingRef = useRef<{
    token: string;
    email: string;
    password: string;
    rememberMe: boolean;
  } | null>(null);

  // Restore session on mount — also handle SSO callback (?sso_token=)
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ssoToken = params.get("sso_token");
    if (ssoToken) {
      storeToken(ssoToken, false);
      // Strip the query param from URL without reloading
      window.history.replaceState({}, "", window.location.pathname);
    }
    const storedToken = ssoToken ?? getStoredToken();
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
          clearStoredToken();
        }
      })
      .catch(() => { clearStoredToken(); })
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(async (email: string, password: string, rememberMe = false) => {
    const res = await fetch(`${ADMIN_BASE}/dev-auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password, remember_me: rememberMe }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `Login failed (${res.status})`);
    }
    const data = await res.json();

    if (data.must_change_password) {
      pendingRef.current = { token: data.token, email, password, rememberMe };
      setMustChangePassword(true);
      return;
    }

    storeToken(data.token, rememberMe);
    setToken(data.token);
    setDeveloper(data);
    const m = await fetchMemberships(data.developer_id, data.token);
    setMemberships(m);
  }, []);

  const changePassword = useCallback(async (newPassword: string) => {
    const pending = pendingRef.current;
    if (!pending) throw new Error("No pending session");

    const res = await fetch(`${ADMIN_BASE}/dev-auth/change-password`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": `Bearer ${pending.token}`,
      },
      body: JSON.stringify({ current_password: pending.password, new_password: newPassword }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? "Failed to change password");
    }

    // Re-login with new password
    const loginRes = await fetch(`${ADMIN_BASE}/dev-auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: pending.email, password: newPassword, remember_me: pending.rememberMe }),
    });
    if (!loginRes.ok) throw new Error("Re-login after password change failed");
    const loginData = await loginRes.json();

    pendingRef.current = null;
    setMustChangePassword(false);
    storeToken(loginData.token, pending.rememberMe);
    setToken(loginData.token);
    setDeveloper(loginData);
    const m = await fetchMemberships(loginData.developer_id, loginData.token);
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
    storeToken(data.token, false);
    setToken(data.token);
    setDeveloper(data);
    const m = await fetchMemberships(data.developer_id, data.token);
    setMemberships(m);
  }, []);

  const logout = useCallback(async () => {
    const storedToken = getStoredToken();
    if (storedToken) {
      await fetch(`${ADMIN_BASE}/dev-auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${storedToken}` },
      }).catch(() => {});
    }
    clearStoredToken();
    pendingRef.current = null;
    setMustChangePassword(false);
    setToken(null);
    setDeveloper(null);
    setMemberships([]);
  }, []);

  const selectTeam = useCallback(async (teamId: string) => {
    const storedToken = getStoredToken();
    if (!storedToken) return;
    const res = await fetch(`${ADMIN_BASE}/dev-auth/select-team?team_id=${encodeURIComponent(teamId)}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${storedToken}` },
    });
    if (res.ok) {
      const data = await res.json();
      setDeveloper(data);
      const m = await fetchMemberships(data.developer_id, storedToken);
      setMemberships(m);
    }
  }, []);

  return (
    <AuthContext.Provider value={{ developer, token, loading, memberships, mustChangePassword, login, register, changePassword, logout, selectTeam, setDeveloper }}>
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
