"use client";

import "./_styles/portal.css";
import { AuthProvider } from "./_lib/authContext";
import PortalShell from "./_components/PortalShell";
import AuthGate from "./_components/AuthGate";
import AiHelpWidget from "./_components/AiHelpWidget";

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <AuthGate>
        <div className="papp">
          <PortalShell />
          {children}
          <AiHelpWidget />
        </div>
      </AuthGate>
    </AuthProvider>
  );
}
