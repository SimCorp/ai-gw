import * as React from "react";
import {
  LayoutGrid,
  Activity,
  Users,
  Shield,
  ShieldCheck,
  Gauge,
  Inbox,
  Box,
  Plug2,
  Sparkles,
  Puzzle,
  Database,
  Plug,
  ClipboardList,
  Bell,
  Key,
  BarChart3,
  FileText,
  Bot,
  BookOpen,
  Home,
} from "lucide-react";
import { UserAvatar } from "./UserAvatar";
import { Topbar, type Crumb } from "./Topbar";

export interface NavItem {
  id: string;
  label: string;
  href: string;
  icon: React.ReactNode;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export interface ShellUser {
  name: string;
  email: string;
  role: string;
}

export interface ShellProps {
  surface: "admin" | "portal";
  nav: NavGroup[];
  activeId: string;
  user: ShellUser;
  crumbs?: Crumb[];
  children?: React.ReactNode;
}

// ── Admin Shell ──────────────────────────────────────────────

function AdminSidebar({
  nav,
  activeId,
  user,
}: {
  nav: NavGroup[];
  activeId: string;
  user: ShellUser;
}) {
  const initials = user.name
    .split(" ")
    .map((p) => p[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <div className="sidebar__logo" aria-hidden="true">
          SC
        </div>
        <div className="sidebar__brand-text">
          <span className="sidebar__brand-name">AI Gateway</span>
          <span className="sidebar__brand-sub">SimCorp Platform</span>
        </div>
      </div>

      {nav.map((group) => (
        <div className="sidebar__group" key={group.label}>
          <div className="sidebar__label">{group.label}</div>
          <nav className="sidebar__nav" aria-label={group.label}>
            {group.items.map((item) => (
              <a
                key={item.id}
                href={item.href}
                className={item.id === activeId ? "is-active" : undefined}
                aria-current={item.id === activeId ? "page" : undefined}
              >
                <span className="ico" aria-hidden="true">
                  {item.icon}
                </span>
                <span>{item.label}</span>
              </a>
            ))}
          </nav>
        </div>
      ))}

      <div className="sidebar__bottom">
        <div className="sidebar__user">
          <div className="sidebar__avatar" aria-hidden="true">
            {initials}
          </div>
          <div className="sidebar__user-meta">
            <div className="sidebar__user-name">{user.name}</div>
            <div className="sidebar__user-role">{user.role}</div>
          </div>
        </div>
      </div>
    </aside>
  );
}

// ── Portal Sidebar ────────────────────────────────────────────

function PortalSidebar({
  nav,
  activeId,
  user,
}: {
  nav: NavGroup[];
  activeId: string;
  user: ShellUser;
}) {
  return (
    <aside className="psidebar">
      <div className="psidebar__brand">
        <div className="logo" aria-hidden="true">
          SC
        </div>
        <div>
          <div className="name">AI Portal</div>
          <div className="sub">SimCorp Platform</div>
        </div>
      </div>

      <nav className="psidebar__nav" aria-label="Portal navigation">
        {nav.map((group) => (
          <React.Fragment key={group.label}>
            <div className="group">{group.label}</div>
            {group.items.map((item) => (
              <a
                key={item.id}
                href={item.href}
                className={item.id === activeId ? "is-active" : undefined}
                aria-current={item.id === activeId ? "page" : undefined}
              >
                {item.icon}
                <span>{item.label}</span>
              </a>
            ))}
          </React.Fragment>
        ))}
      </nav>

      <div className="psidebar__user">
        <UserAvatar email={user.email} size="md" />
        <div className="who">
          <div className="name">{user.name}</div>
          <div className="team">{user.role}</div>
        </div>
      </div>
    </aside>
  );
}

// ── Shell ─────────────────────────────────────────────────────

export function Shell({
  surface,
  nav,
  activeId,
  user,
  crumbs = [],
  children,
}: ShellProps) {
  const isAdmin = surface === "admin";

  return (
    <div
      className={isAdmin ? "app" : "papp"}
      data-surface={surface}
      style={{ fontFamily: "var(--font-sans)", color: "var(--fg-1)", background: "var(--bg)" }}
    >
      {isAdmin ? (
        <AdminSidebar nav={nav} activeId={activeId} user={user} />
      ) : (
        <PortalSidebar nav={nav} activeId={activeId} user={user} />
      )}

      <div className={isAdmin ? "main" : ""}>
        <Topbar crumbs={crumbs} surface={surface} />
        <div className={isAdmin ? "page" : "pmain"}>
          {children}
        </div>
      </div>
    </div>
  );
}

// ── Admin nav definition ──────────────────────────────────────

const ICON_SIZE = 16;

export const ADMIN_NAV: NavGroup[] = [
  {
    label: "Overview",
    items: [
      { id: "dashboard", label: "Dashboard", href: "/admin/dashboard", icon: <LayoutGrid size={ICON_SIZE} /> },
      { id: "requests", label: "Live requests", href: "/admin/requests", icon: <Activity size={ICON_SIZE} /> },
    ],
  },
  {
    label: "Govern",
    items: [
      { id: "teams", label: "Teams", href: "/admin/teams", icon: <Users size={ICON_SIZE} /> },
      { id: "policies", label: "Policies", href: "/admin/policies", icon: <Shield size={ICON_SIZE} /> },
      { id: "guardrails", label: "Guardrails", href: "/admin/guardrails", icon: <ShieldCheck size={ICON_SIZE} /> },
      { id: "quotas", label: "Quotas & budgets", href: "/admin/quotas", icon: <Gauge size={ICON_SIZE} /> },
      { id: "approvals", label: "Approvals", href: "/admin/approvals", icon: <Inbox size={ICON_SIZE} /> },
    ],
  },
  {
    label: "Catalog",
    items: [
      { id: "models", label: "Model registry", href: "/admin/models", icon: <Box size={ICON_SIZE} /> },
      { id: "mcp", label: "MCP servers", href: "/admin/mcp", icon: <Plug2 size={ICON_SIZE} /> },
      { id: "skills", label: "Skills", href: "/admin/skills", icon: <Sparkles size={ICON_SIZE} /> },
      { id: "plugins", label: "Plugins", href: "/admin/plugins", icon: <Puzzle size={ICON_SIZE} /> },
      { id: "cache", label: "Cache", href: "/admin/cache", icon: <Database size={ICON_SIZE} /> },
      { id: "providers", label: "Providers", href: "/admin/providers", icon: <Plug size={ICON_SIZE} /> },
    ],
  },
  {
    label: "Operate",
    items: [
      { id: "alerts", label: "Alerts", href: "/admin/alerts", icon: <Bell size={ICON_SIZE} /> },
      { id: "audit", label: "Audit log", href: "/admin/audit", icon: <ClipboardList size={ICON_SIZE} /> },
    ],
  },
];

export const PORTAL_NAV: NavGroup[] = [
  {
    label: "Use",
    items: [
      { id: "home", label: "Home", href: "/portal", icon: <Home size={ICON_SIZE} /> },
      { id: "playground", label: "Playground", href: "/portal/playground", icon: <Sparkles size={ICON_SIZE} /> },
    ],
  },
  {
    label: "Build",
    items: [
      { id: "prompts", label: "Prompts", href: "/portal/prompts", icon: <FileText size={ICON_SIZE} /> },
      { id: "agents", label: "Agents", href: "/portal/agents", icon: <Bot size={ICON_SIZE} /> },
      { id: "mcp", label: "MCP", href: "/portal/mcp", icon: <Plug2 size={ICON_SIZE} /> },
      { id: "skills", label: "Skills", href: "/portal/skills", icon: <Sparkles size={ICON_SIZE} /> },
      { id: "plugins", label: "Plugins", href: "/portal/plugins", icon: <Puzzle size={ICON_SIZE} /> },
    ],
  },
  {
    label: "Account",
    items: [
      { id: "keys", label: "Keys", href: "/portal/keys", icon: <Key size={ICON_SIZE} /> },
      { id: "usage", label: "Usage", href: "/portal/usage", icon: <BarChart3 size={ICON_SIZE} /> },
      { id: "models", label: "Models", href: "/portal/models", icon: <Box size={ICON_SIZE} /> },
      { id: "docs", label: "Docs", href: "/portal/docs", icon: <BookOpen size={ICON_SIZE} /> },
    ],
  },
];

// ── Preset components ─────────────────────────────────────────

export interface AdminShellProps
  extends Omit<ShellProps, "surface" | "nav"> {
  nav?: NavGroup[];
}

export function AdminShell({ nav = ADMIN_NAV, ...props }: AdminShellProps) {
  return <Shell surface="admin" nav={nav} {...props} />;
}

export interface PortalShellProps
  extends Omit<ShellProps, "surface" | "nav"> {
  nav?: NavGroup[];
}

export function PortalShell({ nav = PORTAL_NAV, ...props }: PortalShellProps) {
  return <Shell surface="portal" nav={nav} {...props} />;
}
