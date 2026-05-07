import * as React from "react";
import { cn } from "../lib/cn";

export interface StatusDotProps extends React.HTMLAttributes<HTMLSpanElement> {
  status: "good" | "warn" | "bad" | "info";
}

export function StatusDot({ status, className, ...props }: StatusDotProps) {
  return (
    <span
      className={cn("statusdot", `statusdot--${status}`, className)}
      {...props}
    />
  );
}
