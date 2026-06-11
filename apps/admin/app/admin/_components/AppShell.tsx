'use client';

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useTheme } from 'next-themes';
import { LogOut } from 'lucide-react';
import {
  RailShell,
  AppTopbar,
  CommandPalette,
  ThemeToggle,
  activePageFor,
  type Crumb,
} from '@aigw/ui';
import { ADMIN_NAV } from '../_nav';
import { getAdminToken, clearAdminToken } from '../../../lib/adminAuth';

const ADMIN_API = process.env.NEXT_PUBLIC_ADMIN_API ?? 'http://localhost:8005';

function SignOutButton() {
  const router = useRouter();

  async function handleSignOut() {
    const token = getAdminToken();
    if (token) {
      try {
        await fetch(`${ADMIN_API}/admin-auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch {
        // Best-effort — clear locally regardless
      }
    }
    clearAdminToken();
    router.replace('/login');
  }

  return (
    <button type="button" className="icon-btn" onClick={handleSignOut} title="Sign out" aria-label="Sign out">
      <LogOut size={15} />
    </button>
  );
}

export function AppShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const router = useRouter();
  const { theme, setTheme } = useTheme();
  const [paletteOpen, setPaletteOpen] = useState(false);

  const { domain, page } = activePageFor(ADMIN_NAV, path);
  const crumbs: Crumb[] = [
    { label: domain?.label ?? 'Admin', href: domain?.href },
    ...(page ? [{ label: page.label }] : []),
  ];

  return (
    <RailShell
      domains={ADMIN_NAV}
      activePath={path}
      brandSuffix="/admin"
      LinkComponent={Link}
      footer={
        <>
          <ThemeToggle theme={theme} setTheme={setTheme} />
          <SignOutButton />
        </>
      }
      topbar={
        <AppTopbar
          crumbs={crumbs}
          onOpenPalette={() => setPaletteOpen(true)}
          LinkComponent={Link}
          actions={
            <span className="env-pill">
              <span className="dot" />
              dev
            </span>
          }
        />
      }
    >
      <CommandPalette
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        domains={ADMIN_NAV}
        onNavigate={href => router.push(href)}
      />
      {children}
    </RailShell>
  );
}
