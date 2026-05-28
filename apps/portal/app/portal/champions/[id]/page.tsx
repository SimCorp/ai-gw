"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

interface ChampionProfile {
  developer_id: string;
  bio: string | null;
  focus_areas: string[];
  office_hours_text: string | null;
  active: boolean;
}

export default function ChampionProfilePage() {
  const params = useParams<{ id: string }>();
  const id = params?.id;
  const [profile, setProfile] = useState<ChampionProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    fetch(`${ADMIN_BASE}/champions/${id}`)
      .then((r) => {
        if (r.status === 404) return Promise.reject("Champion not found");
        if (!r.ok) return Promise.reject(`Error ${r.status}`);
        return r.json();
      })
      .then((data: ChampionProfile) => setProfile(data))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [id]);

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <Link
            href="/portal/champions"
            style={{ fontSize: 12, color: "var(--fg-3)", textDecoration: "none" }}
          >
            ← Back to champions
          </Link>
          <h1 style={{ marginTop: 4 }}>Champion profile</h1>
        </div>
      </div>

      {loading && <div style={{ color: "var(--fg-3)", fontSize: 14 }}>Loading…</div>}
      {error && (
        <div style={{ color: "var(--bad)", fontSize: 13 }}>{error}</div>
      )}

      {profile && (
        <div className="card" style={{ padding: "20px 24px", maxWidth: 720 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 18 }}>
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: "50%",
                background: "var(--sc-blue)",
                color: "white",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 600,
                fontSize: 18,
              }}
            >
              {profile.developer_id.slice(0, 2).toUpperCase()}
            </div>
            <div>
              <div style={{ fontSize: 16, fontWeight: 600, color: "var(--fg-1)" }}>
                Champion {profile.developer_id.slice(0, 8)}
              </div>
              <div style={{ fontSize: 12, color: "var(--fg-3)", marginTop: 2 }}>
                {profile.active ? "Active champion" : "Inactive"}
              </div>
            </div>
          </div>

          {profile.bio && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, color: "var(--fg-3)", marginBottom: 4 }}>Bio</div>
              <div style={{ fontSize: 13, color: "var(--fg-1)", lineHeight: 1.6 }}>{profile.bio}</div>
            </div>
          )}

          {profile.focus_areas.length > 0 && (
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, color: "var(--fg-3)", marginBottom: 6 }}>Focus areas</div>
              <div>
                {profile.focus_areas.map((f) => (
                  <span
                    key={f}
                    style={{
                      display: "inline-block",
                      fontSize: 11,
                      padding: "2px 8px",
                      borderRadius: 999,
                      background: "rgba(8,62,167,0.08)",
                      color: "var(--sc-blue)",
                      marginRight: 4,
                      marginTop: 4,
                    }}
                  >
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          {profile.office_hours_text && (
            <div>
              <div style={{ fontSize: 12, color: "var(--fg-3)", marginBottom: 4 }}>Office hours</div>
              <div style={{ fontSize: 13, color: "var(--fg-1)", lineHeight: 1.6, whiteSpace: "pre-wrap" }}>
                {profile.office_hours_text}
              </div>
            </div>
          )}
        </div>
      )}
    </main>
  );
}
