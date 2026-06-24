import { render } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

vi.mock('next-themes', () => ({ ThemeProvider: ({ children }: { children: React.ReactNode }) => <>{children}</> }));
vi.mock('next/script', () => ({ default: (props: Record<string, string>) => <script data-testid="rybbit-script" {...props} /> }));

describe('RootLayout (portal) — Rybbit tracker', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('injects tracker script when all three env vars are set', async () => {
    vi.stubEnv('NEXT_PUBLIC_RYBBIT_ENABLED', 'true');
    vi.stubEnv('NEXT_PUBLIC_RYBBIT_URL', 'https://rybbit.aigw.scdom.net');
    vi.stubEnv('NEXT_PUBLIC_RYBBIT_SITE_ID', 'site-456');
    const { default: RootLayout } = await import('./layout');
    const { queryByTestId } = render(<RootLayout><div /></RootLayout>);
    expect(queryByTestId('rybbit-script')).not.toBeNull();
  });

  it('omits tracker script when RYBBIT_URL is empty', async () => {
    vi.stubEnv('NEXT_PUBLIC_RYBBIT_ENABLED', 'true');
    vi.stubEnv('NEXT_PUBLIC_RYBBIT_URL', '');
    vi.stubEnv('NEXT_PUBLIC_RYBBIT_SITE_ID', 'site-456');
    const { default: RootLayout } = await import('./layout');
    const { queryByTestId } = render(<RootLayout><div /></RootLayout>);
    expect(queryByTestId('rybbit-script')).toBeNull();
  });

  it('omits tracker script when RYBBIT_SITE_ID is empty', async () => {
    vi.stubEnv('NEXT_PUBLIC_RYBBIT_ENABLED', 'true');
    vi.stubEnv('NEXT_PUBLIC_RYBBIT_URL', 'https://rybbit.aigw.scdom.net');
    vi.stubEnv('NEXT_PUBLIC_RYBBIT_SITE_ID', '');
    const { default: RootLayout } = await import('./layout');
    const { queryByTestId } = render(<RootLayout><div /></RootLayout>);
    expect(queryByTestId('rybbit-script')).toBeNull();
  });
});
