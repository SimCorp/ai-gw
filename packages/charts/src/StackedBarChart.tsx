import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  TooltipProps,
  ReferenceLine,
} from "recharts";

export interface StackedBarSeries {
  key: string;
  color: string;
  label: string;
  /** If true, values are rendered as negative bars (e.g. cache savings). */
  negative?: boolean;
}

export interface StackedBarChartProps {
  data: Record<string, string | number>[];
  series: StackedBarSeries[];
  /** Key to use as the x-axis. Defaults to "time". */
  xKey?: string;
  /** Chart height in px. Defaults to 240. */
  height?: number;
}

function CustomTooltip({
  active,
  payload,
  label,
}: TooltipProps<number, string>): React.ReactElement | null {
  if (!active || !payload?.length) return null;

  return (
    <div
      style={{
        background: "var(--surface-2, #1e2130)",
        border: "1px solid var(--border, rgba(255,255,255,0.08))",
        borderRadius: 6,
        padding: "8px 12px",
        fontSize: 12,
        color: "var(--fg-1, #e2e8f0)",
        boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
      }}
    >
      <div style={{ marginBottom: 4, color: "var(--fg-3, #64748b)" }}>
        {label}
      </div>
      {payload.map((entry) => {
        const raw = entry.value as number;
        return (
          <div
            key={entry.dataKey as string}
            style={{ display: "flex", gap: 8, alignItems: "center" }}
          >
            <span
              style={{
                display: "inline-block",
                width: 8,
                height: 8,
                borderRadius: 2,
                background: entry.color,
                flexShrink: 0,
              }}
            />
            <span style={{ color: "var(--fg-2, #94a3b8)" }}>{entry.name}:</span>
            <span style={{ fontFamily: "var(--font-mono, monospace)" }}>
              {raw < 0 ? `−${Math.abs(raw)}` : raw}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Recharts stacked bar chart supporting negative bars for savings/offsets.
 * The `negative` flag on a series causes its data to be inverted before
 * rendering so it renders below the zero line, matching the portal/usage.html
 * pattern for cache-savings columns.
 */
export function StackedBarChart({
  data,
  series,
  xKey = "time",
  height = 240,
}: StackedBarChartProps): React.ReactElement {
  // Transform negative series values in-flight
  const transformed = data.map((row) => {
    const next: Record<string, string | number> = { ...row };
    for (const s of series) {
      if (s.negative && typeof next[s.key] === "number") {
        next[s.key] = -(next[s.key] as number);
      }
    }
    return next;
  });

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={transformed}
        margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        stackOffset="sign"
      >
        <CartesianGrid
          strokeDasharray="0"
          stroke="rgba(255,255,255,0.05)"
          vertical={false}
        />
        <XAxis
          dataKey={xKey}
          tick={{ fill: "var(--fg-3, #64748b)", fontSize: 11 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: "var(--fg-3, #64748b)", fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          width={40}
        />
        <Tooltip content={<CustomTooltip />} />
        <Legend
          wrapperStyle={{ fontSize: 11, color: "var(--fg-3, #64748b)" }}
        />
        <ReferenceLine y={0} stroke="rgba(255,255,255,0.12)" />
        {series.map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            stackId="a"
            fill={s.color}
            radius={[1, 1, 0, 0]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
