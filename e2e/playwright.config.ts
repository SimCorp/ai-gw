import { defineConfig } from '@playwright/test';

/**
 * Browser E2E quality walkthrough of the AI Gateway portals.
 *
 * Targets a DEPLOYED environment (default: the dev VM, reachable only in-VNet /
 * over ZPA). Credentials and base URL come from the environment — the
 * `scripts/e2e-quality.sh` runner populates them from `pass`. This project is
 * intentionally NOT a CI merge gate (see docs/ops-runbook.md "Quality tests").
 */
const BASE_URL = process.env.E2E_BASE_URL ?? 'https://dev.aigw.scdom.net';

export default defineConfig({
  testDir: './tests',
  // A full portal walkthrough shares one authenticated tab per portal (the apps
  // keep their token in sessionStorage), so each spec file runs serially.
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // list = live terminal output; html = rich report (traces/screenshots on
  // failure); json = machine-readable results for parsing / dashboards / alerts.
  reporter: [
    ['list'],
    ['html', { open: 'never' }],
    ['json', { outputFile: 'results.json' }],
  ],
  use: {
    baseURL: BASE_URL,
    ignoreHTTPSErrors: true, // SimCorp Issuing CA cert is not in the default trust store
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    navigationTimeout: 30_000,
  },
  projects: [
    { name: 'dev-portal', testMatch: /dev-portal\.spec\.ts/ },
    { name: 'admin-portal', testMatch: /admin-portal\.spec\.ts/ },
  ],
});
