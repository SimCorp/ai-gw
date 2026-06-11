"use client";

import * as React from "react";
import { cn } from "../lib/cn";
import { BrandMark } from "./BrandMark";

export interface NavPage {
  href: string;
  label: string;
  /** Optional group heading within the contextual panel. */
  group?: string;
}

export interface NavDomain {
  id: string;
  label: string;
  icon: React.ReactNode;
  /** Landing href when the domain icon is clicked (usually pages[0].href). */
  href: string;
  pages: NavPage[];
}

type LinkLike = React.ComponentType<{
  href: string;
  className?: string;
  children: React.ReactNode;
  onClick?: React.MouseEventHandler;
}>;

export interface RailShellProps {
  domains: NavDomain[];
  /** Current pathname (without basePath), used to derive active domain/page. */
  activePath: string;
  /** Tiny mono suffix under the brand mark, e.g. "/admin" or "/dev". */
  brandSuffix?: string;
  /** Bottom-of-rail slot: theme toggle, user/team menu, sign out. */
  footer?: React.ReactNode;
  /** Topbar rendered above the content area. */
  topbar?: React.ReactNode;
  /** Link component (pass next/link's Link); defaults to <a>. */
  LinkComponent?: LinkLike;
  /** localStorage key for the panel collapse state. */
  storageKey?: string;
  children: React.ReactNode;
}

function matchScore(path: string, href: string): number {
  if (path === href) return href.length + 1;
  if (path.startsWith(href.endsWith("/") ? href : `${href}/`)) return href.length;
  return -1;
}

/** Pick the domain owning the current path (longest matching page/domain href). */
export function activeDomainFor(domains: NavDomain[], path: string): NavDomain | undefined {
  let best: NavDomain | undefined;
  let bestScore = -1;
  for (const d of domains) {
    for (const candidate of [d.href, ...d.pages.map(p => p.href)]) {
      const s = matchScore(path, candidate);
      if (s > bestScore) {
        bestScore = s;
        best = d;
      }
    }
  }
  return best;
}

/** Resolve the active domain and page for a path (for breadcrumbs). */
export function activePageFor(
  domains: NavDomain[],
  path: string,
): { domain?: NavDomain; page?: NavPage } {
  const domain = activeDomainFor(domains, path);
  if (!domain) return {};
  let page: NavPage | undefined;
  let best = -1;
  for (const p of domain.pages) {
    const s = matchScore(path, p.href);
    if (s > best) {
      best = s;
      page = p;
    }
  }
  return { domain, page: best >= 0 ? page : undefined };
}

const DefaultLink: LinkLike = ({ href, ...rest }) => <a href={href} {...rest} />;

export function RailShell({
  domains,
  activePath,
  brandSuffix,
  footer,
  topbar,
  LinkComponent = DefaultLink,
  storageKey = "aigw:panel",
  children,
}: RailShellProps) {
  const [collapsed, setCollapsed] = React.useState(false);
  React.useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem(storageKey) === "collapsed") {
      setCollapsed(true);
    }
  }, [storageKey]);

  const togglePanel = () => {
    setCollapsed(c => {
      const next = !c;
      localStorage.setItem(storageKey, next ? "collapsed" : "open");
      return next;
    });
  };

  const active = activeDomainFor(domains, activePath);
  const Link = LinkComponent;

  const pageScores = (active?.pages ?? []).map(p => matchScore(activePath, p.href));
  const bestPageScore = Math.max(-1, ...pageScores);

  let lastGroup: string | undefined;

  return (
    <div className={cn("rail-app", collapsed && "is-panel-collapsed")}>
      <nav className="rail" aria-label="Domains">
        <div className="rail__brand">
          <BrandMark size={26} />
          {brandSuffix && <span className="rail__suffix">{brandSuffix}</span>}
        </div>
        <div className="rail__nav">
          {domains.map(d => (
            <Link
              key={d.id}
              href={d.href}
              className={cn("rail__item", active?.id === d.id && "is-active")}
            >
              {d.icon}
              <span className="rail__tip">{d.label}</span>
            </Link>
          ))}
        </div>
        {footer && <div className="rail__foot">{footer}</div>}
      </nav>

      <aside className="ctxpanel" aria-label={active?.label}>
        <div className="ctxpanel__head">
          <span className="ctxpanel__title">{active?.label ?? ""}</span>
          <button
            type="button"
            className="icon-btn"
            style={{ width: 22, height: 22, border: 0, background: "transparent" }}
            onClick={togglePanel}
            title="Collapse panel"
            aria-label="Collapse panel"
          >
            ‹
          </button>
        </div>
        <div className="ctxpanel__nav">
          {active?.pages.map((p, i) => {
            const heading =
              p.group && p.group !== lastGroup ? (
                <div key={`g-${p.group}`} className="ctxpanel__group">
                  {p.group}
                </div>
              ) : null;
            lastGroup = p.group;
            const isActive = bestPageScore >= 0 && pageScores[i] === bestPageScore;
            return (
              <React.Fragment key={p.href}>
                {heading}
                <Link href={p.href} className={cn(isActive && "is-active")}>
                  {p.label}
                </Link>
              </React.Fragment>
            );
          })}
        </div>
      </aside>

      <main className="main" style={{ minWidth: 0 }}>
        {collapsed && (
          <button
            type="button"
            className="rail-app__expand icon-btn"
            onClick={togglePanel}
            title="Expand panel"
            aria-label="Expand panel"
          >
            ›
          </button>
        )}
        {topbar}
        {children}
      </main>
    </div>
  );
}
