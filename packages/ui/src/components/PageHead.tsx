import * as React from "react";
import { cn } from "../lib/cn";

export interface PageHeadProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
  className?: string;
}

export function PageHead({ title, subtitle, actions, className }: PageHeadProps) {
  return (
    <div className={cn("page__head", className)}>
      <div>
        <h1 className="page__title">{title}</h1>
        {subtitle && <p className="page__sub">{subtitle}</p>}
      </div>
      {actions && <div className="page__actions">{actions}</div>}
    </div>
  );
}
