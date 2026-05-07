"use client";

import React, { useState } from "react";
import { MOCK_SKILLS, MOCK_RECENT_SKILLS } from "../_lib/mock-data";
import type { Skill } from "../_lib/types";

const SKILL_TABS = ["All", "Mine", "Team", "Org-shared", "Starred"] as const;

const VARIANT_STYLES: Record<string, { icon: string; hover: string }> = {
  "s-purple": { icon: "linear-gradient(135deg,#818CF8 0%,#C084FC 100%)", hover: "rgba(192,132,252,0.5)" },
  "s-teal":   { icon: "linear-gradient(135deg,#2DD4BF 0%,#34D399 100%)", hover: "rgba(45,212,191,0.5)" },
  "s-pink":   { icon: "linear-gradient(135deg,#F472B6 0%,#FB923C 100%)", hover: "rgba(244,114,182,0.5)" },
  "s-blue":   { icon: "linear-gradient(135deg,#3B82F6 0%,#818CF8 100%)", hover: "rgba(129,140,248,0.5)" },
  "s-amber":  { icon: "linear-gradient(135deg,#FBBF24 0%,#F472B6 100%)", hover: "rgba(251,191,36,0.5)" },
};
const ICON_COLOR: Record<string, string> = {
  "s-purple": "#fff", "s-teal": "#052E22", "s-pink": "#fff", "s-blue": "#fff", "s-amber": "#2A0E10",
};

function SkillCard({ skill }: { skill: Skill; key?: React.Key }) {
  const v = VARIANT_STYLES[skill.variant];
  return (
    <div
      style={{
        background: "var(--surface)", border: "1px solid var(--rule)", borderRadius: "var(--radius-3)",
        padding: 18, display: "flex", flexDirection: "column", gap: 10,
        transition: "border-color 120ms, transform 120ms, box-shadow 120ms",
        cursor: "pointer", minHeight: 220,
      }}
      onMouseEnter={(e: React.MouseEvent<HTMLDivElement>) => {
        (e.currentTarget as HTMLElement).style.transform = "translateY(-2px)";
        (e.currentTarget as HTMLElement).style.borderColor = v.hover;
        (e.currentTarget as HTMLElement).style.boxShadow = `0 12px 28px ${v.hover.replace("0.5", "0.18")}`;
      }}
      onMouseLeave={(e: React.MouseEvent<HTMLDivElement>) => {
        (e.currentTarget as HTMLElement).style.transform = "";
        (e.currentTarget as HTMLElement).style.borderColor = "";
        (e.currentTarget as HTMLElement).style.boxShadow = "";
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div style={{
          width: 38, height: 38, borderRadius: 10,
          background: v.icon, color: ICON_COLOR[skill.variant],
          display: "grid", placeItems: "center", flexShrink: 0,
          boxShadow: `0 6px 18px ${v.hover.replace("0.5", "0.35")}`,
        }}>
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" width={20} height={20}>
            <path d={skill.iconPath} />
          </svg>
        </div>
        <div>
          <div style={{ fontWeight: 600, fontSize: 14.5, lineHeight: 1.2 }}>{skill.name}</div>
          <div style={{ fontSize: 11.5, color: "var(--fg-3)", fontFamily: "var(--font-mono)" }}>
            {skill.version} · {skill.model}
          </div>
        </div>
      </div>
      <div style={{ fontSize: 12.5, color: "var(--fg-2)", lineHeight: 1.5, flex: 1 }}>{skill.description}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 11.5, color: "var(--fg-3)" }}>
        {skill.usesPerWeek > 0 ? (
          <>
            <span><strong style={{ color: "var(--fg-1)" }}>{skill.tools}</strong> tools</span>
            <span><strong style={{ color: "var(--fg-1)" }}>{skill.usesPerWeek}</strong> uses/wk</span>
          </>
        ) : (
          <span>used <strong style={{ color: "var(--fg-1)" }}>{skill.usesPerWeek === 0 ? "2h ago" : ""}</strong></span>
        )}
        <span style={{ marginLeft: "auto" }}>★ {skill.stars}</span>
      </div>
    </div>
  );
}

export default function SkillsPage() {
  const [tab, setTab] = useState(0);

  return (
    <main className="pmain">
      <style>{`
        .sgrid { display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }
        .tabs-skill { display:flex; gap:18px; border-bottom:1px solid var(--rule); margin:18px 0 16px; }
        .tabs-skill a { padding:10px 0; font-size:13px; color:var(--fg-2); border-bottom:2px solid transparent; font-weight:500; cursor:pointer; }
        .tabs-skill a.is-active { color:var(--fg-1); border-bottom-color:#818CF8; }
        .tabs-skill .count { font-size:11px; color:var(--fg-3); margin-left:4px; font-variant-numeric:tabular-nums; }
      `}</style>

      <div className="phero">
        <div>
          <h1>Skills</h1>
          <p>Reusable capability bundles — prompt + tool config + examples — that any agent or playground session can import. <strong>22 skills</strong> in your org library.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn">Import from URL</button>
          <button className="btn btn--primary">+ New skill</button>
        </div>
      </div>

      <div className="tabs-skill">
        {[["All", 22], ["Mine", 4], ["Team", 9], ["Org-shared", 22], ["Starred", 6]].map(([label, count], i) => (
          <a key={label} className={tab === i ? "is-active" : ""} onClick={() => setTab(i)}>
            {label} <span className="count">{count}</span>
          </a>
        ))}
      </div>

      <div className="section-h">
        <h2>Featured by platform-team</h2>
        <a href="#" className="a">View library →</a>
      </div>
      <div className="sgrid">
        {MOCK_SKILLS.map((skill) => <SkillCard key={skill.id} skill={skill} />)}
      </div>

      <div className="section-h">
        <h2>Recently used by you</h2>
        <a href="#" className="a">All recent →</a>
      </div>
      <div className="sgrid">
        {MOCK_RECENT_SKILLS.map((skill) => <SkillCard key={skill.id} skill={skill} />)}
      </div>
    </main>
  );
}
