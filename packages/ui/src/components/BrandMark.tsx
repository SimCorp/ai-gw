import * as React from "react";
import { cn } from "../lib/cn";

export interface BrandMarkProps {
  /** Pixel size of the square mark. */
  size?: number;
  /** Render the "ai-gw" wordmark next to the mark. */
  wordmark?: boolean;
  /** Tiny mono suffix after the wordmark, e.g. "/admin" or "/dev". */
  suffix?: string;
  className?: string;
}

/**
 * ai-gw "circuit node" mark: a diamond node with gradient trace lines
 * in (indigo) and out (fuchsia). Gradient colors follow the theme's
 * --trace-from / --trace-to tokens.
 */
export function BrandMark({ size = 28, wordmark = false, suffix, className }: BrandMarkProps) {
  const id = React.useId();
  return (
    <span className={cn("brandmark", className)}>
      <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="var(--trace-from, #6366F1)" />
            <stop offset="1" stopColor="var(--trace-to, #D946EF)" />
          </linearGradient>
        </defs>
        <line x1="1" y1="16" x2="6" y2="16" stroke="var(--trace-from, #6366F1)" strokeWidth="1.6" />
        <line x1="26" y1="16" x2="31" y2="16" stroke="var(--trace-to, #D946EF)" strokeWidth="1.6" />
        <rect
          x="10"
          y="10"
          width="12"
          height="12"
          rx="2.5"
          transform="rotate(45 16 16)"
          fill="none"
          stroke={`url(#${id})`}
          strokeWidth="1.8"
        />
        <circle cx="16" cy="16" r="2" fill={`url(#${id})`} />
      </svg>
      {wordmark && (
        <span className="brandmark__word">
          ai-gw
          {suffix && <span className="brandmark__suffix">{suffix}</span>}
        </span>
      )}
    </span>
  );
}
