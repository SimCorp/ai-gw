import * as React from "react";
import { cn } from "../lib/cn";

export interface KpiGridProps {
  children: React.ReactNode;
  cols?: 2 | 3 | 4;
  className?: string;
}

const colStyles: Record<NonNullable<KpiGridProps["cols"]>, React.CSSProperties> = {
  2: { gridTemplateColumns: "repeat(2, 1fr)" },
  3: { gridTemplateColumns: "repeat(3, 1fr)" },
  4: { gridTemplateColumns: "repeat(4, 1fr)" },
};

export function KpiGrid({ children, cols = 4, className }: KpiGridProps) {
  return (
    <div
      className={cn("kpi-grid", className)}
      style={cols !== 4 ? colStyles[cols] : undefined}
    >
      {children}
    </div>
  );
}
