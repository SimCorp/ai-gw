"use client";

import * as React from "react";
import { Command } from "cmdk";
import { ArrowRight, CornerDownLeft } from "lucide-react";
import type { NavDomain } from "./RailShell";

export interface CommandAction {
  id: string;
  label: string;
  hint?: string;
  icon?: React.ReactNode;
  perform: () => void;
}

export interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  domains: NavDomain[];
  actions?: CommandAction[];
  /** Navigate via the app's router (basePath-aware). */
  onNavigate: (href: string) => void;
}

/**
 * ⌘K command palette indexing all nav pages plus app-provided actions.
 * Controlled, but registers the ⌘K / Ctrl+K hotkey itself.
 */
export function CommandPalette({ open, onOpenChange, domains, actions = [], onNavigate }: CommandPaletteProps) {
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        onOpenChange(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  const go = (href: string) => {
    onOpenChange(false);
    onNavigate(href);
  };

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command palette"
      overlayClassName="cmdk-overlay"
      contentClassName="cmdk-panel"
    >
      <Command.Input placeholder="Search pages and actions…" />
      <Command.List>
        <Command.Empty>No results.</Command.Empty>
        {actions.length > 0 && (
          <Command.Group heading="Actions">
            {actions.map(a => (
              <Command.Item
                key={a.id}
                value={`action ${a.label}`}
                onSelect={() => {
                  onOpenChange(false);
                  a.perform();
                }}
              >
                {a.icon ?? <CornerDownLeft />}
                {a.label}
                {a.hint && <span className="cmdk-item__hint">{a.hint}</span>}
              </Command.Item>
            ))}
          </Command.Group>
        )}
        {domains.map(d => (
          <Command.Group key={d.id} heading={d.label}>
            {d.pages.map(p => (
              <Command.Item
                key={p.href}
                value={`${d.label} ${p.group ?? ""} ${p.label}`}
                onSelect={() => go(p.href)}
              >
                <ArrowRight />
                {p.label}
                <span className="cmdk-item__hint">{p.href}</span>
              </Command.Item>
            ))}
          </Command.Group>
        ))}
      </Command.List>
    </Command.Dialog>
  );
}
