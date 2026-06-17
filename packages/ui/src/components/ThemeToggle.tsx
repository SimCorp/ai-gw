"use client";

import * as React from "react";
import { Sun, Moon, Monitor } from "lucide-react";

export interface ThemeToggleProps {
  /** Current theme setting: "light" | "dark" | "system" (next-themes `theme`). */
  theme: string | undefined;
  setTheme: (theme: string) => void;
}

const ORDER = ["light", "dark", "system"] as const;

/**
 * Tri-state theme toggle (light → dark → system). Receives next-themes'
 * hook values as props so @aigw/ui stays dependency-free.
 */
export function ThemeToggle({ theme, setTheme }: ThemeToggleProps) {
  // Avoid hydration mismatch: theme is undefined server-side.
  const [mounted, setMounted] = React.useState(false);
  React.useEffect(() => setMounted(true), []);

  const current = mounted ? (theme ?? "system") : "system";
  const next = ORDER[(ORDER.indexOf(current as (typeof ORDER)[number]) + 1) % ORDER.length];
  const Icon = current === "light" ? Sun : current === "dark" ? Moon : Monitor;

  return (
    <button
      type="button"
      className="icon-btn"
      onClick={() => setTheme(next)}
      title={`Theme: ${current} (click for ${next})`}
      aria-label={`Switch theme to ${next}`}
    >
      <Icon size={15} />
    </button>
  );
}
