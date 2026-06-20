"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "../../_lib/authContext";

const ADMIN_BASE = process.env.NEXT_PUBLIC_ADMIN_BASE_URL ?? "http://localhost:8005";

interface Booking {
  booking_id: string;
  champion_id: string;
  requested_by: string;
  slot_text: string;
  topic: string | null;
  status: string;
  created_at?: string;
}

const STATUS_COLOR: Record<string, string> = {
  requested: "var(--fg-3)",
  confirmed: "var(--accent)",
  done: "var(--good)",
  cancelled: "var(--bad)",
};

export default function BookingsPage() {
  const { developer, token } = useAuth();
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState<string | null>(null);

  const championId = developer?.developer_id;

  const refresh = useCallback(async () => {
    if (!championId) return;
    setError(null);
    try {
      const res = await fetch(`${ADMIN_BASE}/champions/${championId}/bookings`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setBookings(Array.isArray(data) ? data : (data.bookings ?? []));
    } catch (e) {
      setError(String(e));
      setBookings([]);
    }
  }, [championId, token]);

  useEffect(() => { refresh(); }, [refresh]);

  async function act(bookingId: string, action: "confirm" | "done" | "cancel") {
    setActing(bookingId + action);
    try {
      const res = await fetch(`${ADMIN_BASE}/champions/bookings/${bookingId}/${action}`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (res.ok) await refresh();
    } finally {
      setActing(null);
    }
  }

  return (
    <main className="pmain">
      <div className="phero">
        <div>
          <h1>Bookings</h1>
          <p>Session requests sent to you as a champion.</p>
        </div>
      </div>

      {error && <div style={{ color: "var(--bad)", fontSize: 13, marginBottom: 12 }}>{error}</div>}

      {bookings === null ? (
        <div style={{ color: "var(--fg-3)", fontSize: 13 }}>Loading…</div>
      ) : bookings.length === 0 ? (
        <div className="card" style={{ padding: 20, color: "var(--fg-3)", fontSize: 13 }}>
          No bookings yet. (If you&apos;re not a registered champion, this list will always be empty.)
        </div>
      ) : (
        <div className="card" style={{ overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--rule)", textAlign: "left" }}>
                <th style={{ padding: "10px 14px", fontWeight: 500, color: "var(--fg-3)", fontSize: 12 }}>Slot</th>
                <th style={{ padding: "10px 14px", fontWeight: 500, color: "var(--fg-3)", fontSize: 12 }}>Topic</th>
                <th style={{ padding: "10px 14px", fontWeight: 500, color: "var(--fg-3)", fontSize: 12 }}>Requested by</th>
                <th style={{ padding: "10px 14px", fontWeight: 500, color: "var(--fg-3)", fontSize: 12 }}>Status</th>
                <th style={{ padding: "10px 14px", fontWeight: 500, color: "var(--fg-3)", fontSize: 12 }}></th>
              </tr>
            </thead>
            <tbody>
              {bookings.map((b) => (
                <tr key={b.booking_id} style={{ borderBottom: "1px solid var(--rule)" }}>
                  <td style={{ padding: "10px 14px", color: "var(--fg-1)", whiteSpace: "pre-wrap" }}>{b.slot_text}</td>
                  <td style={{ padding: "10px 14px", color: "var(--fg-2)" }}>{b.topic ?? "—"}</td>
                  <td style={{ padding: "10px 14px", color: "var(--fg-2)", fontFamily: "ui-monospace, monospace", fontSize: 12 }}>
                    {b.requested_by.slice(0, 8)}…
                  </td>
                  <td style={{ padding: "10px 14px" }}>
                    <span style={{
                      fontSize: 11, padding: "2px 8px", borderRadius: 999,
                      border: `1px solid ${STATUS_COLOR[b.status] ?? "var(--rule)"}`,
                      color: STATUS_COLOR[b.status] ?? "var(--fg-3)",
                    }}>{b.status}</span>
                  </td>
                  <td style={{ padding: "10px 14px", textAlign: "right" }}>
                    <div style={{ display: "inline-flex", gap: 6 }}>
                      {b.status === "requested" && (
                        <>
                          <button
                            onClick={() => act(b.booking_id, "confirm")}
                            disabled={acting === b.booking_id + "confirm"}
                            className="btn btn--primary"
                            style={{ fontSize: 12, padding: "4px 10px" }}
                          >Confirm</button>
                          <button
                            onClick={() => act(b.booking_id, "cancel")}
                            disabled={acting === b.booking_id + "cancel"}
                            className="btn"
                            style={{ fontSize: 12, padding: "4px 10px" }}
                          >Cancel</button>
                        </>
                      )}
                      {b.status === "confirmed" && (
                        <>
                          <button
                            onClick={() => act(b.booking_id, "done")}
                            disabled={acting === b.booking_id + "done"}
                            className="btn btn--primary"
                            style={{ fontSize: 12, padding: "4px 10px" }}
                          >Mark done</button>
                          <button
                            onClick={() => act(b.booking_id, "cancel")}
                            disabled={acting === b.booking_id + "cancel"}
                            className="btn"
                            style={{ fontSize: 12, padding: "4px 10px" }}
                          >Cancel</button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div style={{ marginTop: 16, fontSize: 12, color: "var(--fg-3)" }}>
        <Link href="/champions" style={{ color: "var(--accent-text)" }}>← Back to champions</Link>
      </div>
    </main>
  );
}
