"use client";

import * as React from "react";
import { Search } from "lucide-react";

export interface Crumb {
  label: string;
  href?: string;
}

type LinkLike = React.ComponentType<{
  href: string;
  className?: string;
  children: React.ReactNode;
}>;

export interface AppTopbarProps {
  crumbs: Crumb[];
  /** Opens the command palette. */
  onOpenPalette?: () => void;
  /** Right-side slot (env pill, actions). */
  actions?: React.ReactNode;
  LinkComponent?: LinkLike;
}

const DefaultLink: LinkLike = ({ href, ...rest }) => <a href={href} {...rest} />;

export function AppTopbar({ crumbs, onOpenPalette, actions, LinkComponent = DefaultLink }: AppTopbarProps) {
  const Link = LinkComponent;
  return (
    <header className="apptopbar">
      <nav className="crumbs" aria-label="Breadcrumb">
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <React.Fragment key={`${c.label}-${i}`}>
              {i > 0 && <span className="sep">/</span>}
              {last || !c.href ? (
                <span className={last ? "now" : undefined}>{c.label}</span>
              ) : (
                <Link href={c.href}>{c.label}</Link>
              )}
            </React.Fragment>
          );
        })}
      </nav>
      <div className="apptopbar__spacer" />
      {onOpenPalette && (
        <button type="button" className="cmdk-btn" onClick={onOpenPalette}>
          <Search size={13} />
          <span>Search or jump to…</span>
          <kbd>⌘K</kbd>
        </button>
      )}
      {actions}
    </header>
  );
}
