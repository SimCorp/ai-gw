"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useRef } from "react";
import { useAuth } from "../_lib/authContext";

const NAV = [
  {
    group: "Use",
    items: [
      { href: "/portal",            label: "Home",        icon: <HomeIcon /> },
      { href: "/portal/playground", label: "Playground",  icon: <PlayIcon />, kbd: "⌘P" },
      { href: "/portal/agents",     label: "Agents",      icon: <AgentIcon /> },
      { href: "/portal/workflows",  label: "Workflows",   icon: <WorkflowIcon /> },
      { href: "/portal/keys",       label: "API keys",    icon: <KeyIcon /> },
      { href: "/portal/models",     label: "Models",      icon: <CubeIcon /> },
      { href: "/portal/prompts",    label: "Prompts",     icon: <PromptIcon /> },
      { href: "/portal/mcp",        label: "MCP servers", icon: <McpIcon /> },
      { href: "/portal/plugins",    label: "Plugins",     icon: <PluginIcon /> },
      { href: "/portal/skills",     label: "Skills",      icon: <SkillIcon /> },
      { href: "/portal/docs",       label: "Quickstart",  icon: <DocIcon /> },
    ],
  },
  {
    group: "League",
    items: [
      { href: "/portal/league",              label: "Challenges",   icon: <SwordIcon /> },
      { href: "/portal/league/leaderboard",  label: "Leaderboard",  icon: <TrophyIcon /> },
      { href: "/portal/league/results",      label: "My Results",   icon: <ResultsIcon /> },
      { href: "/portal/league/store",        label: "Store",        icon: <StoreIcon /> },
    ],
  },
  {
    group: "Account",
    items: [
      { href: "/portal/usage",          label: "Usage & spend",   icon: <ChartIcon /> },
      { href: "/portal/transformation", label: "AI Transformation", icon: <TransformIcon /> },
      { href: "/portal/champions",      label: "Champions",         icon: <TrophyIcon /> },
      { href: "/portal/settings",       label: "Settings",         icon: <SettingsIcon /> },
    ],
  },
];

export default function PortalShell() {
  const path = usePathname();
  const { developer, logout, selectTeam, memberships } = useAuth();
  const [teamOpen, setTeamOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const teamRef = useRef<HTMLDivElement>(null);
  const userRef = useRef<HTMLDivElement>(null);

  const isActive = (href: string) => {
    if (href === "/portal") return path === "/portal";
    if (href === "/portal/league") return path === "/portal/league";
    return path.startsWith(href);
  };

  // Close dropdowns on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (teamRef.current && !teamRef.current.contains(e.target as Node)) setTeamOpen(false);
      if (userRef.current && !userRef.current.contains(e.target as Node)) setUserOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const initials = developer?.display_name
    ? developer.display_name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase()
    : "?";

  const currentTeam = memberships.find(m => m.team_id === developer?.team_id) ?? null;

  return (
    <aside className="psidebar">
      <div className="psidebar__brand">
        <div className="logo">AI</div>
        <div>
          <div className="name">AI Portal</div>
          <div className="sub" style={{ display: "flex", alignItems: "center", gap: 4 }}>
            {currentTeam?.area_color && (
              <span style={{
                width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                background: currentTeam.area_color,
                display: "inline-block",
              }} />
            )}
            {currentTeam?.area_name
              ? `${currentTeam.area_name} / ${currentTeam.team_name}`
              : (developer?.team_name ?? "no team")}
          </div>
        </div>
      </div>

      <nav className="psidebar__nav">
        {NAV.map((section) => (
          <div key={section.group}>
            <div className="group">{section.group}</div>
            {section.items.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={isActive(item.href) ? "is-active" : ""}
              >
                {item.icon}
                {item.label}
                {"kbd" in item && item.kbd && (
                  <span className="kbd">{item.kbd}</span>
                )}
              </Link>
            ))}
          </div>
        ))}
      </nav>

      <div className="psidebar__user" style={{ flexDirection: "column", alignItems: "stretch", gap: 8 }}>
        {/* Team picker */}
        <div ref={teamRef} style={{ position: "relative" }}>
          <button
            onClick={() => setTeamOpen(v => !v)}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "5px 10px",
              border: "1px solid var(--rule)",
              borderRadius: "var(--radius-2, 6px)",
              background: "var(--surface)",
              color: "var(--fg-1)",
              cursor: "pointer", fontSize: 12.5,
              fontFamily: "inherit", width: "100%",
            }}
          >
            <span style={{
              width: 7, height: 7, borderRadius: "50%",
              background: currentTeam?.area_color ?? (developer?.team_id ? "var(--good, #1F8A5B)" : "var(--fg-3)"),
              flexShrink: 0,
            }} />
            <span style={{ flex: 1, textAlign: "left", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {currentTeam
                ? (currentTeam.area_name ? `${currentTeam.area_name} / ${currentTeam.team_name}` : currentTeam.team_name)
                : (developer?.team_name ?? "Select team")}
            </span>
            <span style={{ color: "var(--fg-3)", fontSize: 10 }}>▾</span>
          </button>

          {teamOpen && (
            <div style={{
              position: "absolute", bottom: "calc(100% + 4px)", left: 0, right: 0,
              background: "var(--surface)", border: "1px solid var(--rule)",
              borderRadius: "var(--radius-3, 8px)",
              boxShadow: "0 4px 16px rgba(0,0,0,0.12)", zIndex: 100, overflow: "hidden",
            }}>
              {memberships.length === 0 ? (
                <div style={{
                  padding: "12px 14px",
                  fontSize: 12.5, color: "var(--fg-3)",
                  fontStyle: "italic",
                }}>
                  Not assigned to any teams — contact your admin
                </div>
              ) : memberships.map(m => {
                const isActive = m.team_id === developer?.team_id;
                return (
                  <button
                    key={m.membership_id}
                    onClick={async () => { await selectTeam(m.team_id); setTeamOpen(false); }}
                    style={{
                      display: "block", width: "100%", textAlign: "left",
                      padding: "9px 12px",
                      background: isActive ? "var(--surface-soft, rgba(0,0,0,0.04))" : "transparent",
                      border: 0, borderBottom: "1px solid var(--rule)",
                      cursor: "pointer", fontSize: 12.5, color: "var(--fg-1)", fontFamily: "inherit",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{
                        width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                        background: m.area_color ?? "var(--fg-3)",
                      }} />
                      <span style={{ fontWeight: isActive ? 600 : 400, flex: 1 }}>{m.team_name}</span>
                      <span style={{
                        fontSize: 10.5, padding: "1px 5px",
                        borderRadius: 4,
                        background: m.role === "admin" ? "var(--accent-soft, rgba(10,123,215,0.1))" : "var(--surface-soft, rgba(0,0,0,0.06))",
                        color: m.role === "admin" ? "var(--sc-link, #0A7BD7)" : "var(--fg-3)",
                        fontWeight: 500,
                      }}>
                        {m.role}
                      </span>
                      {isActive && (
                        <span style={{ fontSize: 10, color: "var(--good, #1F8A5B)", fontWeight: 600 }}>●</span>
                      )}
                    </div>
                    {m.area_name && (
                      <div style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 2, paddingLeft: 12 }}>{m.area_name}</div>
                    )}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {/* User row */}
        <div ref={userRef} style={{ position: "relative" }}>
          <button
            onClick={() => setUserOpen(v => !v)}
            style={{
              display: "flex", alignItems: "center", gap: 10,
              width: "100%", background: "none", border: 0,
              cursor: "pointer", padding: "2px 0", textAlign: "left",
            }}
          >
            <div className="avatar" style={{ flexShrink: 0 }}>{initials}</div>
            <div className="who" style={{ flex: 1, minWidth: 0 }}>
              <div className="name" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {developer?.display_name ?? "—"}
              </div>
              <div className="team" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {developer?.email ?? ""}
              </div>
              {currentTeam && (
                <div style={{
                  fontSize: 10.5, color: "var(--fg-3)",
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  marginTop: 1,
                }}>
                  Team: {currentTeam.area_name ? `${currentTeam.area_name} / ${currentTeam.team_name}` : currentTeam.team_name}
                </div>
              )}
            </div>
            <span style={{ color: "var(--fg-3)", fontSize: 10, flexShrink: 0 }}>▾</span>
          </button>

          {userOpen && (
            <div style={{
              position: "absolute", bottom: "calc(100% + 4px)", left: 0, right: 0,
              background: "var(--surface)", border: "1px solid var(--rule)",
              borderRadius: "var(--radius-3, 8px)",
              boxShadow: "0 4px 16px rgba(0,0,0,0.12)", zIndex: 100, overflow: "hidden",
            }}>
              <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--rule)" }}>
                <div style={{ fontSize: 12.5, fontWeight: 500 }}>{developer?.display_name}</div>
                <div style={{ fontSize: 11.5, color: "var(--fg-3)", marginTop: 2 }}>{developer?.email}</div>
              </div>
              <button
                onClick={async () => { setUserOpen(false); await logout(); }}
                style={{
                  display: "block", width: "100%", textAlign: "left",
                  padding: "10px 12px",
                  background: "transparent", border: 0,
                  cursor: "pointer", fontSize: 13, color: "var(--bad)",
                  fontFamily: "inherit",
                }}
              >
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

/* ── Icons ────────────────────────────────────────────────────── */

function HomeIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 6.5l6-4.5 6 4.5V13.5a.5.5 0 01-.5.5h-3V10h-5v4H2.5a.5.5 0 01-.5-.5V6.5z"/>
    </svg>
  );
}
function PlayIcon() {
  return <svg viewBox="0 0 16 16" fill="currentColor"><path d="M5 3.5v9l8-4.5-8-4.5z"/></svg>;
}
function KeyIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="5.5" cy="8" r="3"/><path d="M8.5 8h5M11.5 8v2"/>
    </svg>
  );
}
function ChartIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 13V8M6 13V5M10 13V3M14 13V7"/>
    </svg>
  );
}
function CubeIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 2L14 5.5v5L8 14 2 10.5v-5L8 2z"/><path d="M8 2v12M2 5.5l6 3.5 6-3.5"/>
    </svg>
  );
}
function DocIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M4 2h6l3 3v9H4V2z"/><path d="M10 2v3h3M6 7h5M6 10h3"/>
    </svg>
  );
}
function PromptIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 3h12v8H2zM5 11l-2 3M11 11l2 3"/>
      <path d="M5 7h6M5 5h3"/>
    </svg>
  );
}
function AgentIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="3" y="5" width="10" height="8" rx="2"/>
      <path d="M8 2v3M5.5 9h0M10.5 9h0"/>
    </svg>
  );
}
function WorkflowIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="3" cy="8" r="2"/>
      <circle cx="13" cy="4" r="2"/>
      <circle cx="13" cy="12" r="2"/>
      <path d="M5 8h3l2-4M5 8h3l2 4"/>
    </svg>
  );
}
function McpIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="5" cy="8" r="2"/><circle cx="11" cy="5" r="2"/><circle cx="11" cy="11" r="2"/>
      <path d="M7 7l2.5-1.5M7 9l2.5 1.5"/>
    </svg>
  );
}
function SkillIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M8 2l1.8 3.6L14 6.5l-3 2.9.7 4.1L8 11.5 4.3 13.5l.7-4.1-3-2.9 4.2-.9L8 2z"/>
    </svg>
  );
}
function PluginIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M6 2v3H2v3h3v1a3 3 0 006 0v-1h3V5h-4V2H6z"/>
    </svg>
  );
}
function SettingsIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="8" cy="8" r="2.5"/>
      <path d="M8 1.5v1M8 13.5v1M1.5 8h1M13.5 8h1M3.2 3.2l.7.7M12.1 12.1l.7.7M3.2 12.8l.7-.7M12.1 3.9l.7-.7"/>
    </svg>
  );
}

function TransformIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 12 L6 8 L9 10 L14 4"/>
      <path d="M11 4h3v3"/>
    </svg>
  );
}
function SwordIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M3 13l10-10M10 3h3v3M5 11l-2 2"/>
    </svg>
  );
}
function TrophyIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M5 2h6v5a3 3 0 01-6 0V2z"/>
      <path d="M5 4H3a2 2 0 002 2M11 4h2a2 2 0 01-2 2M8 9v3M5 14h6"/>
    </svg>
  );
}
function ResultsIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <rect x="2" y="3" width="12" height="10" rx="1.5"/>
      <path d="M5 8h6M5 11h4M5 5h3"/>
    </svg>
  );
}
function StoreIcon() {
  return (
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M2 5h12l-1.5 7H3.5L2 5z"/>
      <path d="M1 2h14M6 5v4M10 5v4"/>
    </svg>
  );
}
