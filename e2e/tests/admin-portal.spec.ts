import { makeAuthedTest } from '../fixtures/auth';
import { defineRouteSuite } from '../lib/routeSuite';

/**
 * Admin portal walkthrough. Explicit route list. basePath is `/admin`, so routes
 * live under `/admin/<page>`.
 */
const test = makeAuthedTest('admin');
const B = '/admin';

test.describe('admin portal', () => {
  // Bare /admin must land on the dashboard (basePath root redirect). curl can't
  // follow the client-side hop, and the route list below hits explicit pages, so
  // this is the only check that exercises the basePath root redirect end to end.
  test('root redirects to dashboard', async ({ authedPage }) => {
    await authedPage.goto(B, { waitUntil: 'domcontentloaded' });
    await authedPage.waitForURL(/\/admin\/dashboard\/?$/, { timeout: 15000 });
  });

  defineRouteSuite(test, [
    { label: 'dashboard', path: `${B}/dashboard` },
    { label: 'alerts', path: `${B}/alerts` },
    { label: 'approvals', path: `${B}/approvals` },
    { label: 'audit', path: `${B}/audit` },
    { label: 'guardrails', path: `${B}/guardrails` },
    { label: 'league-seasons', path: `${B}/league/seasons` },
    { label: 'mcp', path: `${B}/mcp` },
    { label: 'models', path: `${B}/models` },
    { label: 'org', path: `${B}/org` },
    { label: 'plugins', path: `${B}/plugins` },
    { label: 'policies', path: `${B}/policies` },
    { label: 'providers', path: `${B}/providers` },
    { label: 'quotas', path: `${B}/quotas` },
    { label: 'reports', path: `${B}/reports` },
    { label: 'requests', path: `${B}/requests` },
    { label: 'security', path: `${B}/security` },
    { label: 'security-jobs', path: `${B}/security/jobs` },
    { label: 'security-quotas', path: `${B}/security/quotas` },
    { label: 'security-targets', path: `${B}/security/targets` },
    { label: 'settings-entra', path: `${B}/settings/entra` },
    { label: 'settings-sessions', path: `${B}/settings/sessions` },
    { label: 'skills', path: `${B}/skills` },
    { label: 'tools', path: `${B}/tools` },
    { label: 'transformation', path: `${B}/transformation` },
    { label: 'users', path: `${B}/users` },
  ]);
});
