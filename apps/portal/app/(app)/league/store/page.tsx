"use client";

import React, { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import LevelBadge from "../_components/LevelBadge";
import XPBar from "../_components/XPBar";
import { levelFor } from "../_components/level";
import { celebrate } from "../_components/confetti";

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
  const [equipping, setEquipping] = useState<string | null>(null);

  const { data: storeData, isLoading } = useQuery<StoreItem[] | { items?: StoreItem[] }>({
    queryKey: ["portal-store"],
    queryFn: () => fetch(`${LEAGUE}/store/items`).then(r => r.json()),
  });

  const { data: balanceData } = useQuery<PointBalance>({
    queryKey: ["portal-balance"],
    queryFn: () => fetch(`${LEAGUE}/store/balance`).then(r => r.json()),
  });

  const { data: purchasesData } = useQuery<Purchase[] | { purchases?: Purchase[] }>({
    queryKey: ["portal-purchases"],
    queryFn: () => fetch(`${LEAGUE}/store/owned`).then(r => r.json()),
  });

  const { data: equippedData, refetch: refetchEquipped } = useQuery<Array<{id: string; name: string; type: string}>>({
    queryKey: ["portal-equipped"],
    queryFn: () => fetch(`${LEAGUE}/equipped`).then(r => r.ok ? r.json() : []),
  });
  const equippedIds = new Set((equippedData ?? []).map(e => e.id));

  const items = Array.isArray(storeData) ? storeData : storeData?.items ?? [];
  const balance = balanceData?.balance ?? 0;
  const level = levelFor(balanceData?.lifetime_earned ?? 0);
  const ownedIds = new Set(
    Array.isArray(purchasesData)
      ? purchasesData.map(p => p.id)
      : purchasesData?.purchases?.map(p => p.id) ?? []
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
      void celebrate();
    } catch (e: unknown) {
      setBuyError(e instanceof Error ? e.message : "Purchase failed");
    } finally {
      setBuying(null);
    }
  }

  async function handleEquip(itemId: string) {
    setEquipping(itemId);
    try {
      await fetch(`${LEAGUE}/equip/${itemId}`, { method: "POST" });
      qc.invalidateQueries({ queryKey: ["portal-equipped"] });
      refetchEquipped();
    } finally {
      setEquipping(null);
    }
  }

  async function handleUnequip(itemId: string) {
    setEquipping(itemId);
    try {
      await fetch(`${LEAGUE}/equip/${itemId}`, { method: "DELETE" });
      qc.invalidateQueries({ queryKey: ["portal-equipped"] });
      refetchEquipped();
    } finally {
      setEquipping(null);
    }
  }

  return (
    <div className="page">
      <div className="page__head">
        <div>
          <h1 className="page__title">Reward shop</h1>
          <p className="page__sub">Spend your League points on cosmetic rewards</p>
        </div>
        <div className="page__actions">
          <Link href="/league" className="btn">
            ← Quest board
          </Link>
        </div>
      </div>

      {/* Wallet */}
      <div className="lg-wallet">
        <LevelBadge level={level.level} />
        <div>
          <div className="microlabel" style={{ marginBottom: 2 }}>POINT_BALANCE</div>
          <div className="lg-wallet__balance">★ {balance.toLocaleString()}</div>
        </div>
        <div style={{ minWidth: 200, flex: 1, maxWidth: 320 }}>
          <XPBar info={level} />
        </div>
        {balanceData && (
          <>
            <div className="lg-wallet__stat">
              <div className="microlabel">EARNED</div>
              <div className="v" style={{ color: "var(--good)" }}>
                +{(balanceData.lifetime_earned ?? 0).toLocaleString()}
              </div>
            </div>
            <div className="lg-wallet__stat">
              <div className="microlabel">SPENT</div>
              <div className="v" style={{ color: "var(--bad)" }}>
                -{(balanceData.lifetime_spent ?? 0).toLocaleString()}
              </div>
            </div>
          </>
        )}
      </div>

      {equippedData && equippedData.length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div className="microlabel" style={{ marginBottom: 10 }}>CURRENTLY_EQUIPPED</div>
          <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
            {equippedData.map(item => (
              <div
                key={item.id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "8px 14px",
                  borderRadius: 8,
                  background: "var(--good-soft)",
                  border: "1px solid var(--good)",
                }}
              >
                <span style={{ fontSize: 16 }}>{TYPE_ICONS[item.type as ItemType] ?? "✨"}</span>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: "var(--fg-1)" }}>{item.name}</div>
                  <div style={{ fontSize: 11, color: "var(--fg-3)" }}>
                    {TYPE_LABELS[item.type as ItemType] ?? item.type} · equipped
                  </div>
                </div>
                <button
                  type="button"
                  className="btn btn--sm"
                  onClick={() => handleUnequip(item.id)}
                  disabled={equipping === item.id}
                  style={{ marginLeft: 4 }}
                >
                  {equipping === item.id ? "…" : "Unequip"}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {buyError && (
        <div
          style={{
            marginBottom: 16,
            padding: "10px 14px",
            borderRadius: 8,
            fontSize: 13,
            background: "var(--bad-soft)",
            border: "1px solid var(--bad)",
            color: "var(--bad)",
          }}
        >
          {buyError}
        </div>
      )}

      {/* Filter tabs */}
      <div className="lg-seasons">
        {(["all", "badge", "card_border", "avatar_frame", "title"] as const).map(f => (
          <button
            key={f}
            type="button"
            className={`lg-season${filterType === f ? " is-active" : ""}`}
            onClick={() => setFilterType(f)}
          >
            {f === "all" ? "All" : TYPE_LABELS[f] + "s"}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div style={{ textAlign: "center", padding: 60, color: "var(--fg-3)" }}>Loading shop…</div>
      ) : filtered.length === 0 ? (
        <div
          style={{
            textAlign: "center",
            padding: "60px 20px",
            border: "1px dashed var(--rule)",
            borderRadius: 10,
            color: "var(--fg-3)",
          }}
        >
          <div style={{ fontSize: 36, marginBottom: 12 }}>🛒</div>
          <div style={{ fontWeight: 600, marginBottom: 6, color: "var(--fg-1)" }}>Nothing here yet</div>
          <div style={{ fontSize: 13 }}>Check back when new items are added</div>
        </div>
      ) : (
        <div className="lg-rewards">
          {filtered.map(item => {
            const owned = ownedIds.has(item.id);
            const canAfford = balance >= item.point_cost;
            const isExclusive = !!item.exclusive_season_id;
            const isBuying = buying === item.id;

            return (
              <div key={item.id} className={`lg-reward${owned ? " lg-reward--owned" : ""}`}>
                {owned && <div className="lg-reward__flag lg-reward__flag--owned">OWNED</div>}
                {isExclusive && <div className="lg-reward__flag lg-reward__flag--exclusive">EXCLUSIVE</div>}
                <div className="lg-reward__icon">{TYPE_ICONS[item.type]}</div>
                <div className="lg-reward__name">{item.name}</div>
                <div className="lg-reward__type">{TYPE_LABELS[item.type]}</div>
                <div
                  style={{
                    marginTop: "auto",
                    paddingTop: 12,
                    borderTop: "1px dashed var(--rule)",
                    display: "flex",
                    flexDirection: "column",
                    gap: 8,
                  }}
                >
                  <div className="lg-reward__price">
                    {isExclusive ? "Exclusive" : `★ ${item.point_cost.toLocaleString()}`}
                  </div>
                  {!isExclusive && !owned && (
                    <button
                      type="button"
                      className="lg-btn-gold"
                      style={{ justifyContent: "center" }}
                      onClick={() => handleBuy(item)}
                      disabled={!canAfford || isBuying}
                    >
                      {isBuying ? "Buying…" : canAfford ? "Buy" : "Not enough points"}
                    </button>
                  )}
                  {owned && (
                    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                      {equippedIds.has(item.id) ? (
                        <button
                          type="button"
                          className="btn btn--sm"
                          style={{ justifyContent: "center", color: "var(--good)", borderColor: "var(--good)" }}
                          onClick={() => handleUnequip(item.id)}
                          disabled={equipping === item.id}
                        >
                          {equipping === item.id ? "…" : "✓ Equipped · Unequip"}
                        </button>
                      ) : (
                        <button
                          type="button"
                          className="btn btn--sm"
                          style={{ justifyContent: "center" }}
                          onClick={() => handleEquip(item.id)}
                          disabled={equipping === item.id}
                        >
                          {equipping === item.id ? "…" : "Equip"}
                        </button>
                      )}
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
