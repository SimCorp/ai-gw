"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./_lib/authContext";
import PortalShell from "./_components/PortalShell";
import AuthGate from "./_components/AuthGate";
import AiHelpWidget from "./_components/AiHelpWidget";
import MockBoot from "./_components/MockBoot";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <MockBoot>
      <AuthProvider>
        <AuthGate>
          <div className="papp">
            <PortalShell />
            {children}
            <AiHelpWidget />
          </div>
        </AuthGate>
      </AuthProvider>
      </MockBoot>
    </QueryClientProvider>
  );
}
