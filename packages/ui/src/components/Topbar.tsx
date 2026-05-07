import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Bell, Sun, Moon, Search } from "lucide-react";

export interface Crumb {
  label: string;
  href?: string;
}

export interface TopbarProps {
  crumbs: Crumb[];
  surface: "admin" | "portal";
}

export function Topbar({ crumbs, surface }: TopbarProps) {
  const [searchOpen, setSearchOpen] = React.useState(false);
  const [dark, setDark] = React.useState(() => {
    if (typeof window !== "undefined") {
      return (localStorage.getItem("aigw-theme") ?? "dark") === "dark";
    }
    return true;
  });

  const toggleTheme = React.useCallback(() => {
    setDark((d) => {
      const next = !d;
      document.documentElement.setAttribute("data-theme", next ? "dark" : "light");
      localStorage.setItem("aigw-theme", next ? "dark" : "light");
      return next;
    });
  }, []);

  // Open command palette on ⌘K / Ctrl+K
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <header className="topbar" data-surface={surface}>
      {/* Breadcrumbs */}
      <nav className="crumbs" aria-label="Breadcrumb">
        {crumbs.map((crumb, i) => {
          const isLast = i === crumbs.length - 1;
          return (
            <React.Fragment key={i}>
              {i > 0 && <span className="sep" aria-hidden="true">/</span>}
              {isLast ? (
                <span className="now" aria-current="page">{crumb.label}</span>
              ) : (
                <a href={crumb.href ?? "#"}>{crumb.label}</a>
              )}
            </React.Fragment>
          );
        })}
      </nav>

      <span className="topbar__spacer" />

      {/* Environment pill */}
      <span className="env-pill">
        <span className="dot" aria-hidden="true" />
        production
      </span>

      {/* Search button / ⌘K trigger */}
      <Dialog.Root open={searchOpen} onOpenChange={setSearchOpen}>
        <Dialog.Trigger asChild>
          <button
            className="search"
            type="button"
            aria-label="Search (⌘K)"
            style={{ cursor: "pointer" }}
          >
            <Search size={14} aria-hidden="true" />
            <span style={{ flex: 1, textAlign: "left" }}>
              Search teams, keys, requests…
            </span>
            <kbd>⌘K</kbd>
          </button>
        </Dialog.Trigger>

        <Dialog.Portal>
          <Dialog.Overlay
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(15,18,36,0.5)",
              zIndex: 200,
            }}
          />
          <Dialog.Content
            style={{
              position: "fixed",
              top: "20%",
              left: "50%",
              transform: "translateX(-50%)",
              background: "var(--surface)",
              border: "1px solid var(--rule)",
              borderRadius: "var(--radius-3)",
              boxShadow: "var(--shadow-pop)",
              width: 560,
              maxWidth: "90vw",
              zIndex: 201,
              overflow: "hidden",
            }}
            aria-describedby={undefined}
          >
            <Dialog.Title
              style={{
                padding: "14px 16px",
                borderBottom: "1px solid var(--rule)",
                fontWeight: 600,
                fontSize: 13,
                margin: 0,
              }}
            >
              Command palette
            </Dialog.Title>
            <div style={{ padding: "14px 16px" }}>
              <div className="search" style={{ width: "100%" }}>
                <Search size={14} aria-hidden="true" />
                <input
                  autoFocus
                  placeholder="Search teams, models, traces…"
                  style={{ flex: 1 }}
                />
              </div>
              <p style={{ color: "var(--fg-3)", fontSize: 12, marginTop: 12, textAlign: "center" }}>
                Full implementation with results coming in PR2
              </p>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Theme toggle */}
      <button
        type="button"
        className="icon-btn"
        onClick={toggleTheme}
        aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
        title={dark ? "Light mode" : "Dark mode"}
      >
        {dark ? <Sun size={14} /> : <Moon size={14} />}
      </button>

      {/* Notifications */}
      <button
        type="button"
        className="icon-btn"
        aria-label="Notifications"
        title="Notifications"
      >
        <Bell size={14} />
      </button>
    </header>
  );
}
