import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

describe('PortalAnalyticsPage', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('renders iframes when both embed URLs are configured', async () => {
    vi.stubEnv('RYBBIT_EMBED_URL_ADMIN', 'https://rybbit.aigw.scdom.net/embed/1');
    vi.stubEnv('RYBBIT_EMBED_URL_PORTAL', 'https://rybbit.aigw.scdom.net/embed/2');
    const { default: Page } = await import('./page');
    render(<Page />);
    expect(screen.getByTitle('Admin Portal Analytics')).toBeInTheDocument();
    expect(screen.getByTitle('Developer Portal Analytics')).toBeInTheDocument();
  });

  it('renders fallback when embed URLs are not configured', async () => {
    vi.stubEnv('RYBBIT_EMBED_URL_ADMIN', '');
    vi.stubEnv('RYBBIT_EMBED_URL_PORTAL', '');
    const { default: Page } = await import('./page');
    render(<Page />);
    expect(screen.getByText(/RYBBIT_EMBED_URL_ADMIN/)).toBeInTheDocument();
    expect(screen.getByText(/RYBBIT_EMBED_URL_PORTAL/)).toBeInTheDocument();
    expect(screen.queryByTitle('Admin Portal Analytics')).not.toBeInTheDocument();
  });
});
