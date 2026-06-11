import * as React from "react";
import { cn } from "../lib/cn";

export interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  width?: number | string;
  height?: number | string;
}

export function Skeleton({ width, height = 14, className, style, ...props }: SkeletonProps) {
  return (
    <div
      className={cn("skeleton", className)}
      style={{ width, height, ...style }}
      aria-hidden="true"
      {...props}
    />
  );
}
