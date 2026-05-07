import React, { useEffect, useRef } from "react";
import {
  ResponsiveContainer,
  AreaChart as ReAreaChart,
  Area,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  TooltipProps,
} from "recharts";

export interface AreaChartSeries {
  key: string;
  color: string;
  label: string;
}

export interface AreaChartProps {
  data: Record<string, string | number>[];
  series: AreaChartSeries[];
  /** Key to use as the x-axis. Defaults to "time". */
  xKey?: string;
  /** Chart height in px. Defaults to 240. */
  height?: number;
  /** If set, calls onRefresh on this interval (ms). */
  autoRefreshMs?: number;
  onRefresh?: () => void;
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
      {payload.map((entry) => (
        <div
          key={entry.dataKey as string}
          style={{ display: "flex", gap: 8, alignItems: "center" }}
        >
          <span
            style={{
              display: "inline-block",
              width: 8,
              height: 8,
              borderRadius: "50%",
              background: entry.color,
              flexShrink: 0,
            }}
          />
          <span style={{ color: "var(--fg-2, #94a3b8)" }}>
            {entry.name}:
          </span>
          <span style={{ fontFamily: "var(--font-mono, monospace)" }}>
            {entry.value}
          </span>
        </div>
      ))}
    </div>
  );
}

/**
 * Recharts-based area chart with dark-themed styling.
 * Wraps content in ResponsiveContainer as required.
 */
export function AreaChart({
  data,
  series,
  xKey = "time",
  height = 240,
  autoRefreshMs,
  onRefresh,
}: AreaChartProps): React.ReactElement {
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (autoRefreshMs && onRefresh) {
      timerRef.current = setInterval(onRefresh, autoRefreshMs);
      return () => {
        if (timerRef.current !== null) clearInterval(timerRef.current);
      };
    }
    return undefined;
  }, [autoRefreshMs, onRefresh]);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ReAreaChart
        data={data}
        margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
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
        {series.map((s) => (
          <Area
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            fill={s.color}
            fillOpacity={0.15}
            strokeWidth={1.5}
            dot={false}
            activeDot={{ r: 3 }}
          />
        ))}
      </ReAreaChart>
    </ResponsiveContainer>
  );
}
