"use client";

import { useState, useEffect, useRef } from "react";
import { useAuth } from "../_lib/authContext";

/**
 * Rail-footer user button: avatar opens a popover with the current user,
 * team picker, and sign out. Team-switch/auth logic unchanged from the
 * previous PortalShell sidebar.
 */
export default function TeamUserFooter() {
  const { developer, logout, selectTeam, memberships } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const initials = developer?.display_name
    ? developer.display_name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase()
    : "?";

  const currentTeam = memberships.find(m => m.team_id === developer?.team_id) ?? null;

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        title={developer?.display_name ?? "Account"}
        aria-label="Account menu"
        style={{
          width: 30,
          height: 30,
          borderRadius: "50%",
          border: "1px solid var(--rule-strong)",
          background: "var(--accent-soft)",
          color: "var(--accent-text)",
          fontSize: 11,
          fontWeight: 600,
          cursor: "pointer",
          display: "grid",
          placeItems: "center",
          position: "relative",
        }}
      >
        {initials}
        {currentTeam?.area_color && (
          <span
            style={{
              position: "absolute",
              right: -1,
              bottom: -1,
              width: 9,
              height: 9,
              borderRadius: "50%",
              background: currentTeam.area_color,
              border: "2px solid var(--panel-bg)",
            }}
          />
        )}
      </button>

      {open && (
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: "calc(100% + 14px)",
            width: 264,
            background: "var(--surface)",
            border: "1px solid var(--rule)",
            borderRadius: "var(--r-3)",
            boxShadow: "var(--shadow-pop)",
            zIndex: 100,
            overflow: "hidden",
          }}
        >
          <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--rule)" }}>
            <div style={{ fontSize: 12.5, fontWeight: 600 }}>{developer?.display_name ?? "—"}</div>
            <div style={{ fontSize: 11.5, color: "var(--fg-3)", marginTop: 2 }}>{developer?.email ?? ""}</div>
          </div>

          <div
            className="microlabel"
            style={{ padding: "8px 12px 4px" }}
          >
            Team
          </div>
          {memberships.length === 0 ? (
            <div style={{ padding: "4px 12px 12px", fontSize: 12.5, color: "var(--fg-3)", fontStyle: "italic" }}>
              Not assigned to any teams — contact your admin
            </div>
          ) : (
            memberships.map(m => {
              const isActive = m.team_id === developer?.team_id;
              return (
                <button
                  key={m.membership_id}
                  type="button"
                  onClick={async () => {
                    await selectTeam(m.team_id);
                    setOpen(false);
                  }}
                  style={{
                    display: "block",
                    width: "100%",
                    textAlign: "left",
                    padding: "8px 12px",
                    background: isActive ? "var(--accent-soft)" : "transparent",
                    border: 0,
                    cursor: "pointer",
                    fontSize: 12.5,
                    color: "var(--fg-1)",
                    fontFamily: "inherit",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span
                      style={{
                        width: 6,
                        height: 6,
                        borderRadius: "50%",
                        flexShrink: 0,
                        background: m.area_color ?? "var(--fg-3)",
                      }}
                    />
                    <span style={{ fontWeight: isActive ? 600 : 400, flex: 1 }}>{m.team_name}</span>
                    <span
                      style={{
                        fontSize: 10.5,
                        padding: "1px 5px",
                        borderRadius: 4,
                        background: m.role === "admin" ? "var(--accent-soft)" : "var(--surface-soft)",
                        color: m.role === "admin" ? "var(--accent-text)" : "var(--fg-3)",
                        fontWeight: 500,
                      }}
                    >
                      {m.role}
                    </span>
                    {isActive && <span style={{ fontSize: 10, color: "var(--good)", fontWeight: 600 }}>●</span>}
                  </div>
                  {m.area_name && (
                    <div style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 2, paddingLeft: 12 }}>
                      {m.area_name}
                    </div>
                  )}
                </button>
              );
            })
          )}

          <button
            type="button"
            onClick={async () => {
              setOpen(false);
              await logout();
            }}
            style={{
              display: "block",
              width: "100%",
              textAlign: "left",
              padding: "10px 12px",
              background: "transparent",
              border: 0,
              borderTop: "1px solid var(--rule)",
              cursor: "pointer",
              fontSize: 12.5,
              color: "var(--bad)",
              fontFamily: "inherit",
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
