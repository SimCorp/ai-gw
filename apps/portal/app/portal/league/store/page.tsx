"use client";

import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";

const LEAGUE = process.env.NEXT_PUBLIC_LEAGUE_API ?? "http://localhost:8080/league";

type ItemType = "badge" | "card_border" | "avatar_frame" | "title";

interface StoreItem {
  id: string;
  name: string;
  type: ItemType;
  point_cost: number;
  asset_url: string;
  exclusive_season_id: string | null;
  exclusive_top_n: number | null;
}

interface PointBalance {
  balance: number;
  lifetime_earned: number;
  lifetime_spent: number;
}

interface Purchase {
  id: string;
}

const TYPE_ICONS: Record<ItemType, string> = {
  badge: "🏅",
  card_border: "🖼️",
  avatar_frame: "✨",
  title: "🏷️",
};

const TYPE_LABELS: Record<ItemType, string> = {
  badge: "Badge",
  card_border: "Card border",
  avatar_frame: "Avatar frame",
  title: "Title",
};

export default function StorePage() {
  const qc = useQueryClient();
  const [filterType, setFilterType] = useState<"all" | ItemType>("all");
  const [buying, setBuying] = useState<string | null>(null);
  const [buyError, setBuyError] = useState<string | null>(null);

  const { data: storeData, isLoading } = useQuery<StoreItem[]>({
    queryKey: ["portal-store"],
    queryFn: () => fetch(`${LEAGUE}/store/items`).then(r => r.json()),
  });

  const { data: balanceData } = useQuery<PointBalance>({
    queryKey: ["portal-balance"],
    queryFn: () => fetch(`${LEAGUE}/store/balance`).then(r => r.json()),
  });

  const { data: purchasesData } = useQuery<Purchase[]>({
    queryKey: ["portal-purchases"],
    queryFn: () => fetch(`${LEAGUE}/store/owned`).then(r => r.json()),
  });

  const items = Array.isArray(storeData) ? storeData : (storeData as { items?: StoreItem[] })?.items ?? [];
  const balance = balanceData?.balance ?? 0;
  const ownedIds = new Set(
    Array.isArray(purchasesData)
      ? purchasesData.map(p => p.id)
      : (purchasesData as { purchases?: Purchase[] })?.purchases?.map(p => p.id) ?? []
  );

  const filtered = filterType === "all" ? items : items.filter(i => i.type === filterType);

  async function handleBuy(item: StoreItem) {
    setBuying(item.id);
    setBuyError(null);
    try {
      const res = await fetch(`${LEAGUE}/store/purchase/${item.id}`, {
        method: "POST",
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail ?? "Purchase failed");
      }
      qc.invalidateQueries({ queryKey: ["portal-purchases"] });
      qc.invalidateQueries({ queryKey: ["portal-balance"] });
    } catch (e: unknown) {
      setBuyError(e instanceof Error ? e.message : "Purchase failed");
    } finally {
      setBuying(null);
    }
  }

  return (
    <div className="page">
      <div className="page__header">
        <div>
          <h1 className="page__title">Store & Profile</h1>
          <p className="page__sub">Spend your League points on cosmetic rewards</p>
        </div>
        <Link href="/portal/league" style={{
          padding: "7px 14px", borderRadius: 6, border: "1px solid var(--rule)",
          background: "transparent", color: "var(--fg-2)", textDecoration: "none", fontSize: 13,
        }}>← Challenges</Link>
      </div>

      {/* Balance card */}
      <div style={{
        background: "linear-gradient(135deg, rgba(180,83,9,0.2) 0%, rgba(8,62,167,0.12) 100%)",
        border: "1px solid rgba(180,83,9,0.3)",
        borderRadius: 12, padding: "20px 24px", marginBottom: 24,
        display: "flex", alignItems: "center", gap: 24,
      }}>
        <div>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--warn, #B45309)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>
            Point balance
          </div>
          <div style={{ fontSize: 36, fontWeight: 800, fontFamily: "var(--font-mono)", color: "var(--fg-1)" }}>
            ★ {balance.toLocaleString()}
          </div>
        </div>
        {balanceData && (
          <div style={{ borderLeft: "1px solid var(--rule)", paddingLeft: 24, display: "flex", gap: 24 }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--fg-3)", marginBottom: 2 }}>Lifetime earned</div>
              <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--good, #1F8A5B)" }}>
                +{(balanceData.lifetime_earned ?? 0).toLocaleString()}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "var(--fg-3)", marginBottom: 2 }}>Lifetime spent</div>
              <div style={{ fontSize: 18, fontWeight: 700, fontFamily: "var(--font-mono)", color: "var(--bad, #DC2626)" }}>
                -{(balanceData.lifetime_spent ?? 0).toLocaleString()}
              </div>
            </div>
          </div>
        )}
      </div>

      {buyError && (
        <div style={{
          marginBottom: 16, padding: "10px 14px", borderRadius: 8, fontSize: 13,
          background: "rgba(220,38,38,0.1)", border: "1px solid rgba(220,38,38,0.3)", color: "#FCA5A5",
        }}>{buyError}</div>
      )}

      {/* Filter tabs */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {(["all", "badge", "card_border", "avatar_frame", "title"] as const).map(f => (
          <button key={f} onClick={() => setFilterType(f)} style={{
            padding: "6px 14px", borderRadius: 20, fontSize: 12.5, fontWeight: 500,
            border: "1px solid var(--rule)", cursor: "pointer",
            background: filterType === f ? "var(--sc-blue, #083EA7)" : "transparent",
            color: filterType === f ? "#fff" : "var(--fg-2)",
          }}>
            {f === "all" ? "All" : TYPE_LABELS[f] + "s"}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div style={{ textAlign: "center", padding: "60px", color: "var(--fg-3)" }}>Loading store…</div>
      ) : filtered.length === 0 ? (
        <div style={{
          textAlign: "center", padding: "60px 20px",
          border: "1px dashed var(--rule)", borderRadius: 10, color: "var(--fg-3)",
        }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>🛒</div>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Nothing here yet</div>
          <div style={{ fontSize: 13 }}>Check back when new items are added</div>
        </div>
      ) : (
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          gap: 14,
        }}>
          {filtered.map(item => {
            const owned = ownedIds.has(item.id);
            const canAfford = balance >= item.point_cost;
            const isExclusive = !!item.exclusive_season_id;
            const isBuying = buying === item.id;

            return (
              <div key={item.id} style={{
                background: "var(--surface)", border: `1px solid ${owned ? "var(--good, #1F8A5B)" : "var(--rule)"}`,
                borderRadius: 10, padding: "18px 14px", textAlign: "center",
                display: "flex", flexDirection: "column", gap: 10,
                opacity: isExclusive ? 0.7 : 1,
                position: "relative", overflow: "hidden",
              }}>
                {owned && (
                  <div style={{
                    position: "absolute", top: 8, right: 8,
                    fontSize: 10, fontWeight: 700, color: "var(--good, #1F8A5B)",
                    background: "rgba(31,138,91,0.15)", padding: "2px 6px", borderRadius: 4,
                  }}>OWNED</div>
                )}
                {isExclusive && (
                  <div style={{
                    position: "absolute", top: 8, left: 8,
                    fontSize: 10, fontWeight: 700, color: "var(--warn, #B45309)",
                    background: "rgba(180,83,9,0.15)", padding: "2px 6px", borderRadius: 4,
                  }}>EXCLUSIVE</div>
                )}
                <div style={{ fontSize: 40 }}>{TYPE_ICONS[item.type]}</div>
                <div style={{ fontWeight: 600, fontSize: 13 }}>{item.name}</div>
                <div style={{ fontSize: 11.5, color: "var(--fg-3)" }}>{TYPE_LABELS[item.type]}</div>
                <div style={{
                  marginTop: "auto", paddingTop: 12, borderTop: "1px solid var(--rule)",
                  display: "flex", flexDirection: "column", gap: 8,
                }}>
                  <div style={{ fontSize: 16, fontWeight: 700, color: "var(--warn, #B45309)" }}>
                    {isExclusive ? "Exclusive" : `★ ${item.point_cost.toLocaleString()}`}
                  </div>
                  {!isExclusive && !owned && (
                    <button
                      onClick={() => handleBuy(item)}
                      disabled={!canAfford || isBuying}
                      style={{
                        padding: "7px 12px", borderRadius: 6, border: "none",
                        background: canAfford ? "var(--sc-blue, #083EA7)" : "var(--rule)",
                        color: canAfford ? "#fff" : "var(--fg-3)",
                        cursor: canAfford && !isBuying ? "pointer" : "not-allowed",
                        fontSize: 12.5, fontWeight: 600,
                        opacity: isBuying ? 0.7 : 1,
                      }}
                    >
                      {isBuying ? "Buying…" : canAfford ? "Buy" : "Not enough points"}
                    </button>
                  )}
                  {owned && (
                    <div style={{ fontSize: 12.5, color: "var(--good, #1F8A5B)", fontWeight: 500 }}>
                      ✓ In your collection
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
