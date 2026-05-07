import * as React from "react";
import { cn } from "../lib/cn";

export interface FilterBarProps {
  children?: React.ReactNode;
  right?: React.ReactNode;
  className?: string;
}

export function FilterBar({ children, right, className }: FilterBarProps) {
  return (
    <div className={cn("filters", className)}>
      {children}
      {right && (
        <>
          <span style={{ flex: 1 }} />
          {right}
        </>
      )}
    </div>
  );
}
