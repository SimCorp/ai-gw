import { redirect } from 'next/navigation';
import { describe, expect, it, vi } from 'vitest';
import ServiceStatusPage from './page';

vi.mock('next/navigation', () => ({ redirect: vi.fn() }));

describe('ServiceStatusPage', () => {
  it('redirects to /status/', () => {
    ServiceStatusPage();
    expect(redirect).toHaveBeenCalledWith('/status/');
  });
});
