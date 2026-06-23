'use client';

import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthGuard } from './_components/AuthGuard';
import { MockBoot } from './_components/MockBoot';
import { AppShell } from './_components/AppShell';
import AiHelpWidget from './_components/AiHelpWidget';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
    },
  },
});

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <MockBoot>
        <AuthGuard>
          <AppShell>{children}</AppShell>
          <AiHelpWidget />
        </AuthGuard>
      </MockBoot>
    </QueryClientProvider>
  );
}
