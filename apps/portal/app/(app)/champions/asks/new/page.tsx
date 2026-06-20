"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "../../../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

function NewAskForm() {
  const { developer, token } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Pre-populate from query string (used by AiHelpWidget CTA)
  useEffect(() => {
    const qTitle = search?.get("title");
    const qDesc = search?.get("description");
    if (qTitle) setTitle(qTitle);
    if (qDesc) setDescription(qDesc);
  }, [search]);

  const canSubmit = !!developer && title.trim().length > 0 && description.trim().length > 0 && !busy;

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
      const res = await fetch(`${ADMIN_BASE}/champions/asks`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          title: title.trim(),
          description: description.trim(),
          created_by: developer.developer_id,
          team_id: developer.team_id ?? null,
          tags: tags
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `Submit failed (${res.status})`);
      }
      router.push("/champions/asks");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "8px 10px",
    borderRadius: 6,
    border: "1px solid var(--rule)",
    background: "var(--bg)",
    color: "var(--fg-1)",
    fontSize: 13,
  };

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <Link
            href="/champions/asks"
            style={{ fontSize: 12, color: "var(--fg-3)", textDecoration: "none" }}
          >
            ← Back to asks
          </Link>
          <h1 style={{ marginTop: 4 }}>Create an ask</h1>
          <p>Need help from a champion? Describe what you’re trying to do.</p>
        </div>
      </div>

      <form
        onSubmit={submit}
        className="card"
        style={{ padding: "24px 28px", maxWidth: 640, display: "flex", flexDirection: "column", gap: 16 }}
      >
        <div>
          <label style={{ fontSize: 12, color: "var(--fg-3)", display: "block", marginBottom: 6 }}>
            Title
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={busy}
            placeholder="One-line summary"
            style={inputStyle}
          />
        </div>

        <div>
          <label style={{ fontSize: 12, color: "var(--fg-3)", display: "block", marginBottom: 6 }}>
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={busy}
            rows={8}
            placeholder="Context, what you've tried, what you need…"
            style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }}
          />
        </div>

        <div>
          <label style={{ fontSize: 12, color: "var(--fg-3)", display: "block", marginBottom: 6 }}>
            Tags (comma-separated, optional)
          </label>
          <input
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            disabled={busy}
            placeholder="rag, langchain, models"
            style={inputStyle}
          />
        </div>

        {error && <div style={{ color: "var(--bad)", fontSize: 12 }}>{error}</div>}

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
            {busy ? "Submitting…" : "Submit ask"}
          </button>
          <Link href="/champions/asks" className="btn" style={{ fontSize: 13, padding: "8px 16px" }}>
            Cancel
          </Link>
        </div>
      </form>
    </main>
  );
}

export default function NewAskPage() {
  return (
    <Suspense fallback={<main className="pmain"><div style={{ color: "var(--fg-3)", fontSize: 13 }}>Loading…</div></main>}>
      <NewAskForm />
    </Suspense>
  );
}
