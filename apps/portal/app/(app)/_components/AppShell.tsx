"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  RailShell,
  AppTopbar,
  CommandPalette,
  ThemeToggle,
  activePageFor,
  type Crumb,
} from "@aigw/ui";
import { PORTAL_NAV } from "../_nav";
import TeamUserFooter from "./TeamUserFooter";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);

  const { domain, page } = activePageFor(PORTAL_NAV, path);
  const crumbs: Crumb[] = [
    { label: domain?.label ?? "Portal", href: domain?.href },
    ...(page && page.label !== domain?.label ? [{ label: page.label }] : []),
  ];

  return (
    <RailShell
      domains={PORTAL_NAV}
      activePath={path}
      brandSuffix="/dev"
      LinkComponent={Link}
      footer={
        <>
          <ThemeToggle theme={theme} setTheme={setTheme} />
          <TeamUserFooter />
        </>
      }
      topbar={
        <AppTopbar
          crumbs={crumbs}
          onOpenPalette={() => setPaletteOpen(true)}
          LinkComponent={Link}
        />
      }
    >
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        domains={PORTAL_NAV}
        onNavigate={href => router.push(href)}
      />
      {children}
    </RailShell>
  );
}
