"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "../../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

type ContentType = "article" | "link" | "video" | "artifact";

export default function NewContentPage() {
  const { developer, token } = useAuth();
  const router = useRouter();
  const [type, setType] = useState<ContentType>("article");
  const [url, setUrl] = useState("");
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canSubmit = !!developer && (url.trim().length > 0 || text.trim().length > 0) && !busy;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!developer) {
      setError("You must be signed in.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = `Bearer ${token}`;
      const res = await fetch(`${ADMIN_BASE}/champions/content`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          champion_id: developer.developer_id,
          type,
          url: url.trim() || null,
          text: text.trim() || null,
          optional_title: title.trim() || null,
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Submit failed (${res.status})`);
      }
      router.push("/champions");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <Link
            href="/champions"
            style={{ fontSize: 12, color: "var(--fg-3)", textDecoration: "none" }}
          >
            ← Back to champions
          </Link>
          <h1 style={{ marginTop: 4 }}>Share content</h1>
          <p>Submit an article, link, video, or artifact for the champions feed.</p>
        </div>
      </div>

      <form
        onSubmit={submit}
        className="card"
        style={{ padding: "24px 28px", maxWidth: 640, display: "flex", flexDirection: "column", gap: 16 }}
      >
        <div>
          <label style={{ fontSize: 12, color: "var(--fg-3)", display: "block", marginBottom: 6 }}>
            Type
          </label>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as ContentType)}
            disabled={busy}
            style={{
              width: "100%",
              padding: "8px 10px",
              borderRadius: 6,
              border: "1px solid var(--rule)",
              background: "var(--bg)",
              color: "var(--fg-1)",
              fontSize: 13,
            }}
          >
            <option value="article">Article</option>
            <option value="link">Link</option>
            <option value="video">Video</option>
            <option value="artifact">Artifact</option>
          </select>
        </div>

        <div>
          <label style={{ fontSize: 12, color: "var(--fg-3)", display: "block", marginBottom: 6 }}>
            URL
          </label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={busy}
            placeholder="https://…"
            style={{
              width: "100%",
              padding: "8px 10px",
              borderRadius: 6,
              border: "1px solid var(--rule)",
              background: "var(--bg)",
              color: "var(--fg-1)",
              fontSize: 13,
            }}
          />
        </div>

        <div>
          <label style={{ fontSize: 12, color: "var(--fg-3)", display: "block", marginBottom: 6 }}>
            Or paste text
          </label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={busy}
            rows={6}
            placeholder="Paste an article, notes, or summary…"
            style={{
              width: "100%",
              padding: "8px 10px",
              borderRadius: 6,
              border: "1px solid var(--rule)",
              background: "var(--bg)",
              color: "var(--fg-1)",
              fontSize: 13,
              fontFamily: "inherit",
              resize: "vertical",
            }}
          />
        </div>

        <div>
          <label style={{ fontSize: 12, color: "var(--fg-3)", display: "block", marginBottom: 6 }}>
            Title (optional — auto-generated if blank)
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={busy}
            style={{
              width: "100%",
              padding: "8px 10px",
              borderRadius: 6,
              border: "1px solid var(--rule)",
              background: "var(--bg)",
              color: "var(--fg-1)",
              fontSize: 13,
            }}
          />
        </div>

        {error && (
          <div style={{ color: "var(--bad)", fontSize: 12 }}>{error}</div>
        )}

        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button
            type="submit"
            disabled={!canSubmit}
            className="btn btn--primary"
            style={{
              fontSize: 13,
              padding: "8px 16px",
              opacity: canSubmit ? 1 : 0.5,
              cursor: canSubmit ? "pointer" : "not-allowed",
            }}
          >
            {busy ? "Submitting…" : "Submit"}
          </button>
          <Link
            href="/champions"
            className="btn"
            style={{ fontSize: 13, padding: "8px 16px" }}
          >
            Cancel
          </Link>
        </div>
      </form>
    </main>
  );
}
