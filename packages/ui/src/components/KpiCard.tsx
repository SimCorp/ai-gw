import * as React from "react";
import { cn } from "../lib/cn";

export interface KpiDelta {
  label: string;
  direction: "up" | "down" | "flat";
}

export interface KpiCardProps {
  label: string;
  value: string | number;
  unit?: string;
  delta?: KpiDelta;
  sparkline?: React.ReactNode;
  className?: string;
}

export function KpiCard({ label, value, unit, delta, sparkline, className }: KpiCardProps) {
  return (
    <div className={cn("kpi", className)}>
      <div className="kpi__label">{label}</div>
      <div className="kpi__value">
        {value}
        {unit && <span className="unit">{unit}</span>}
      </div>
      {delta && (
        <div className={cn("kpi__delta", delta.direction)}>
          {delta.direction === "up" && "▲ "}
          {delta.direction === "down" && "▼ "}
          {delta.direction === "flat" && "▬ "}
          {delta.label}
        </div>
      )}
      {sparkline && <div className="kpi__spark">{sparkline}</div>}
    </div>
  );
}
