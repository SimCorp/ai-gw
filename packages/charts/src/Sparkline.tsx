import React from "react";

export interface SparklineProps {
  data: number[];
  variant: "line" | "bar" | "area";
  /** CSS color or var() reference. Defaults to var(--accent). */
  color?: string;
  /** px height of the SVG element. Defaults to 28. */
  height?: number;
  /** If set, renders the SVG at this fixed pixel width; otherwise 100% via CSS. */
  width?: number;
}

const VIEW_W = 320;
const VIEW_H = 80;
const BAR_GAP = 2;

function normalize(data: number[]): number[] {
  if (data.length === 0) return [];
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min;
  if (range === 0) return data.map(() => 0.5);
  return data.map((v) => (v - min) / range);
}

function buildLinePath(norm: number[]): string {
  if (norm.length === 0) return "";
  const stepX = VIEW_W / Math.max(norm.length - 1, 1);
  return norm
    .map((v, i) => {
      const x = i * stepX;
      const y = VIEW_H - v * VIEW_H;
      return `${i === 0 ? "M" : "L"}${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
}

function buildAreaPath(norm: number[]): string {
  const linePart = buildLinePath(norm);
  if (!linePart) return "";
  return `${linePart} L${VIEW_W},${VIEW_H} L0,${VIEW_H} Z`;
}

/**
 * Lightweight pure-SVG sparkline with no external chart dependency.
 * viewBox="0 0 320 80" preserveAspectRatio="none"
 * CSS filter: drop-shadow(0 0 6px currentColor) matches reskin-admin.css .kpi__spark
 */
export function Sparkline({
  data,
  variant,
  color = "var(--accent)",
  height = 28,
  width,
}: SparklineProps): React.ReactElement {
  const norm = normalize(data);

  const svgStyle: React.CSSProperties = {
    display: "block",
    height,
    width: width !== undefined ? width : "100%",
    // currentColor in the filter matches the color applied to this element
    color,
    filter: "drop-shadow(0 0 6px currentColor)",
  };

  if (variant === "bar") {
    const barW = (VIEW_W - BAR_GAP * (norm.length - 1)) / Math.max(norm.length, 1);
    const bars = norm.map((v, i) => {
      const barH = v * VIEW_H;
      const x = i * (barW + BAR_GAP);
      const y = VIEW_H - barH;
      return (
        <rect
          key={i}
          x={x.toFixed(2)}
          y={y.toFixed(2)}
          width={Math.max(barW, 0).toFixed(2)}
          height={Math.max(barH, 0).toFixed(2)}
          fill="currentColor"
          rx="1"
        />
      );
    });

    return (
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        style={svgStyle}
        aria-hidden="true"
      >
        {bars}
      </svg>
    );
  }

  if (variant === "area") {
    const linePath = buildLinePath(norm);
    const areaPath = buildAreaPath(norm);
    return (
      <svg
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        preserveAspectRatio="none"
        style={svgStyle}
        aria-hidden="true"
      >
        {areaPath && (
          <path d={areaPath} fill="currentColor" opacity={0.1} />
        )}
        {linePath && (
          <path
            d={linePath}
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
          />
        )}
      </svg>
    );
  }

  // variant === "line" (default)
  const linePath = buildLinePath(norm);
  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      preserveAspectRatio="none"
      style={svgStyle}
      aria-hidden="true"
    >
      {linePath && (
        <path
          d={linePath}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
        />
      )}
    </svg>
  );
}
