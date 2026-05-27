"use client";

import "./_styles/portal.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "./_lib/authContext";
import PortalShell from "./_components/PortalShell";
import AuthGate from "./_components/AuthGate";
import AiHelpWidget from "./_components/AiHelpWidget";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
});

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <AuthGate>
          <div className="papp">
            <PortalShell />
            {children}
            <AiHelpWidget />
          </div>
        </AuthGate>
      </AuthProvider>
    </QueryClientProvider>
  );
}
