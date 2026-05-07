import * as React from "react";
import { cn } from "../lib/cn";

export interface PillProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "info" | "good" | "warn" | "bad";
  dot?: boolean;
}

export function Pill({
  variant = "default",
  dot = false,
  className,
  children,
  ...props
}: PillProps) {
  const variantClass =
    variant === "default" ? "" : `pill--${variant}`;

  return (
    <span className={cn("pill", variantClass, className)} {...props}>
      {dot && <span className="dot" />}
      {children}
    </span>
  );
}
