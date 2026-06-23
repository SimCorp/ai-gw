'use client';

import { useEffect, useState } from 'react';
import { TOKEN_KEY } from '../../../lib/adminAuth';

const MOCKS_ON = process.env.NEXT_PUBLIC_USE_MOCKS === '1';

/**
 * Dev-only mock mode (NEXT_PUBLIC_USE_MOCKS=1): starts the MSW worker and
 * seeds a fake admin session so pages can be eyeballed without the Azure
 * backend. Unhandled requests pass through (and fail → error/empty states).
 */
export function MockBoot({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(!MOCKS_ON);

  useEffect(() => {
    if (!MOCKS_ON) return;
    sessionStorage.setItem(TOKEN_KEY, 'mock-admin-token');
    import('../_mocks/browser')
      .then(({ worker }) =>
        worker.start({
          onUnhandledRequest: 'bypass',
          serviceWorker: { url: '/mockServiceWorker.js' },
        }),
      )
      .then(() => setReady(true));
  }, []);

  if (!ready) return null;
  return <>{children}</>;
}
