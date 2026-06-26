"use client";

import { useState, useEffect } from "react";
import { Skeleton } from "@aigw/ui";
import { useAuth } from "../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

interface SceneElement {
  name: string;
  emoji: string;
  reason: string;
}

interface PortraitData {
  image_base64: string;
  mime: string;
  week_start: string;
  scene_data: Record<string, SceneElement>;
}

export default function UsagePortrait() {
  const { token } = useAuth();
  const [data, setData] = useState<PortraitData | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!token) { setLoading(false); return; }
    fetch(`${ADMIN_BASE}/portrait/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(r => (r.ok ? r.json() : null))
      .then((d: PortraitData | null) => setData(d))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [token]);

  if (!loading && !data) return null;

  return (
    <div className="card" style={{ marginBottom: 14 }}>
      <div className="card__head">
        <h3 className="card__title">Your usage portrait</h3>
        <span className="card__sub">
          {data ? `week of ${data.week_start} · ink sketch` : "generating…"}
        </span>
      </div>
      <div className="card__body">
        {loading ? (
          <Skeleton width="100%" height={240} style={{ borderRadius: "var(--r-2)" }} />
        ) : data ? (
          <>
            <img
              src={`data:${data.mime};base64,${data.image_base64}`}
              alt="Your AI usage portrait"
              style={{
                width: "100%",
                maxWidth: 480,
                borderRadius: "var(--r-2)",
                display: "block",
              }}
            />
            <div style={{ marginTop: 12 }}>
              <button
                className="btn btn--ghost btn--sm"
                onClick={() => setOpen(o => !o)}
                style={{ fontSize: 12.5 }}
              >
                {open ? "▾" : "▸"} What does this mean?
              </button>
              {open && (
                <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 5 }}>
                  {Object.entries(data.scene_data).map(([, el]) => (
                    <div key={el.name} style={{ display: "flex", gap: 10, fontSize: 12.5 }}>
                      <span style={{ width: 20, textAlign: "center", flexShrink: 0 }}>{el.emoji}</span>
                      <span style={{ fontWeight: 500, color: "var(--fg-1)", minWidth: 120 }}>{el.name}</span>
                      <span className="muted">{el.reason}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}
