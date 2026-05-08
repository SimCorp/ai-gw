"use client";

import React, { useState } from "react";
import { useAuth } from "../_lib/authContext";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { developer, loading } = useAuth();

  if (loading) {
    return (
      <div style={{
        minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center",
        background: "var(--bg)", color: "var(--fg-2)", fontSize: 14,
      }}>
        Loading…
      </div>
    );
  }

  if (!developer) {
    return <LoginPage />;
  }

  return <>{children}</>;
}

function LoginPage() {
  const { login, register } = useAuth();
  const [tab, setTab] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (tab === "login") {
        await login(email, password);
      } else {
        if (!displayName.trim()) { setError("Display name is required"); setSubmitting(false); return; }
        await register(email, displayName, password);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--bg)",
      padding: "24px 16px",
    }}>
      {/* Brand */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 36 }}>
        <div style={{
          width: 40, height: 40, borderRadius: 10,
          background: "linear-gradient(135deg, var(--sc-blue), var(--sc-purple))",
          display: "grid", placeItems: "center",
          fontWeight: 800, fontSize: 16, color: "#fff",
        }}>AI</div>
        <div>
          <div style={{ fontWeight: 700, fontSize: 18, color: "var(--fg-1)" }}>AI Gateway</div>
          <div style={{ fontSize: 12, color: "var(--fg-3)" }}>Developer Portal</div>
        </div>
      </div>

      {/* Card */}
      <div style={{
        width: "100%", maxWidth: 400,
        background: "var(--surface)",
        border: "1px solid var(--rule)",
        borderRadius: 12,
        overflow: "hidden",
      }}>
        {/* Tabs */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--rule)" }}>
          {(["login", "register"] as const).map(t => (
            <button
              key={t}
              onClick={() => { setTab(t); setError(null); }}
              style={{
                flex: 1, padding: "13px 0", fontSize: 13.5, fontWeight: 500,
                border: 0, background: tab === t ? "var(--surface)" : "var(--surface-soft, rgba(0,0,0,0.03))",
                color: tab === t ? "var(--fg-1)" : "var(--fg-3)",
                cursor: "pointer", fontFamily: "inherit",
                borderBottom: tab === t ? "2px solid var(--sc-blue)" : "2px solid transparent",
              }}
            >
              {t === "login" ? "Sign in" : "Create account"}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} style={{ padding: "24px 24px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 5 }}>
              Work email
            </label>
            <input
              type="email"
              className="input"
              style={{ width: "100%", boxSizing: "border-box" }}
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              placeholder="you@simcorp.com"
              autoComplete="email"
            />
          </div>

          {tab === "register" && (
            <div>
              <label style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 5 }}>
                Display name
              </label>
              <input
                type="text"
                className="input"
                style={{ width: "100%", boxSizing: "border-box" }}
                value={displayName}
                onChange={e => setDisplayName(e.target.value)}
                required
                placeholder="Your name"
                autoComplete="name"
              />
            </div>
          )}

          <div>
            <label style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 5 }}>
              Password {tab === "register" && <span style={{ color: "var(--fg-3)" }}>(min 8 chars)</span>}
            </label>
            <input
              type="password"
              className="input"
              style={{ width: "100%", boxSizing: "border-box" }}
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              minLength={8}
              placeholder="••••••••"
              autoComplete={tab === "login" ? "current-password" : "new-password"}
            />
          </div>

          {error && (
            <div style={{
              padding: "10px 12px", borderRadius: 6,
              background: "rgba(239,62,74,0.1)", border: "1px solid var(--bad)",
              color: "var(--bad)", fontSize: 13,
            }}>
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn--primary"
            disabled={submitting}
            style={{ width: "100%", marginTop: 4, justifyContent: "center" }}
          >
            {submitting
              ? (tab === "login" ? "Signing in…" : "Creating account…")
              : (tab === "login" ? "Sign in" : "Create account")}
          </button>
        </form>

        {tab === "login" && (
          <div style={{ padding: "0 24px 20px", fontSize: 12, color: "var(--fg-3)", textAlign: "center" }}>
            No account?{" "}
            <button
              onClick={() => setTab("register")}
              style={{ background: "none", border: 0, color: "var(--sc-link, var(--sc-blue))", cursor: "pointer", fontSize: 12, fontFamily: "inherit", padding: 0 }}
            >
              Create one →
            </button>
          </div>
        )}
      </div>

      <div style={{ marginTop: 24, fontSize: 12, color: "var(--fg-3)", textAlign: "center" }}>
        AI Gateway · SimCorp developer platform
      </div>
    </div>
  );
}
