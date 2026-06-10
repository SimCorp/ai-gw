import * as React from "react";

export interface MetricBarProps {
  value: number;
  max: number;
  variant?: "default" | "warn" | "bad";
}

function autoVariant(pct: number): "default" | "warn" | "bad" {
  if (pct >= 90) return "bad";
  if (pct >= 70) return "warn";
  return "default";
}

const FILL_COLORS: Record<string, string> = {
  default: "var(--accent)",
  warn: "var(--warn)",
  bad: "var(--bad)",
};

export function MetricBar({ value, max, variant }: MetricBarProps) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  const resolvedVariant = variant ?? autoVariant(pct);
  const fillColor = FILL_COLORS[resolvedVariant];

  return (
    <div
      role="progressbar"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={max}
      style={{
        position: "relative",
        height: 6,
        background: "var(--surface-soft)",
        borderRadius: 3,
        overflow: "hidden",
        minWidth: 80,
      }}
    >
      <i
        style={{
          position: "absolute",
          inset: "0 auto 0 0",
          width: `${pct}%`,
          background: fillColor,
          borderRadius: 3,
          display: "block",
        }}
      />
    </div>
  );
}
