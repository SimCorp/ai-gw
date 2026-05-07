"use client";

import "./_styles/portal.css";
import PortalShell from "./_components/PortalShell";

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="papp">
      <PortalShell />
      {children}
    </div>
  );
}
