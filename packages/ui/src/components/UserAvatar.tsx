import * as React from "react";
import { cn } from "../lib/cn";

export interface UserAvatarProps {
  email: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

/** Deterministic hue from email string */
function emailToColor(email: string): string {
  let hash = 0;
  for (let i = 0; i < email.length; i++) {
    hash = email.charCodeAt(i) + ((hash << 5) - hash);
  }
  const hue = Math.abs(hash) % 360;
  // Use a fixed saturation and lightness that works on dark backgrounds
  return `hsl(${hue}, 60%, 45%)`;
}

function initials(email: string): string {
  const name = email.split("@")[0];
  const parts = name.split(/[._-]/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

const sizeStyles: Record<NonNullable<UserAvatarProps["size"]>, React.CSSProperties> = {
  sm: { width: 22, height: 22, fontSize: 9 },
  md: { width: 26, height: 26, fontSize: 11 },
  lg: { width: 32, height: 32, fontSize: 13 },
};

export function UserAvatar({ email, size = "md", className }: UserAvatarProps) {
  const bg = emailToColor(email);
  const style: React.CSSProperties = {
    ...sizeStyles[size],
    background: bg,
  };

  return (
    <span
      className={cn("avatar", className)}
      style={style}
      aria-label={email}
      title={email}
    >
      {initials(email)}
    </span>
  );
}
