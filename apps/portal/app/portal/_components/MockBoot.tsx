"use client";

import { useEffect, useState } from "react";

const MOCKS_ON = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

/**
 * Dev-only mock mode (NEXT_PUBLIC_USE_MOCKS=1): starts the MSW worker and
 * seeds a fake developer session before AuthProvider mounts, so the portal
 * can be eyeballed without the Azure backend.
 */
export default function MockBoot({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(!MOCKS_ON);

  useEffect(() => {
    if (!MOCKS_ON) return;
    sessionStorage.setItem("portal_dev_token", "mock-dev-token");
    import("../_mocks/browser")
      .then(({ worker }) =>
        worker.start({
          onUnhandledRequest: "bypass",
          serviceWorker: { url: "/portal/mockServiceWorker.js" },
        }),
      )
      .then(() => setReady(true));
  }, []);

  if (!ready) return null;
  return <>{children}</>;
}
