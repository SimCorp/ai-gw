import { test as base, expect, type Page } from '@playwright/test';
import { Recorder } from '../lib/walk';

/**
 * Auth for the walkthrough.
 *
 * Both portals keep their session token in sessionStorage (dev: `portal_dev_token`,
 * admin: `admin_session_token`), which Playwright's saved `storageState` does NOT
 * persist. So instead of saved auth, a worker-scoped `authedPage` fixture performs
 * the UI login once and yields the live page; route tests navigate IN PLACE on that
 * same tab so the session survives.
 */

type Portal = 'dev' | 'admin';

const CONFIG: Record<Portal, { loginPath: string; emailEnv: string; pwEnv: string }> = {
  dev: { loginPath: '/portal/', emailEnv: 'E2E_DEV_EMAIL', pwEnv: 'E2E_DEV_PW' },
  admin: { loginPath: '/admin-portal/', emailEnv: 'E2E_ADMIN_EMAIL', pwEnv: 'E2E_ADMIN_PW' },
};

interface AuthFixtures {
  authedPage: Page;
  recorder: Recorder;
}

export function makeAuthedTest(portal: Portal) {
  return base.extend<object, AuthFixtures>({
    authedPage: [
      async ({ browser }, use) => {
        const cfg = CONFIG[portal];
        const email = process.env[cfg.emailEnv];
        const pw = process.env[cfg.pwEnv];
        if (!email || !pw) {
          throw new Error(
            `Missing ${cfg.emailEnv}/${cfg.pwEnv}. Run via scripts/e2e-quality.sh (sources creds from pass).`,
          );
        }
        const context = await browser.newContext();
        const page = await context.newPage();
        await page.goto(cfg.loginPath, { waitUntil: 'domcontentloaded' });
        await page.waitForTimeout(1500);
        await page.fill("input[type=email], input[placeholder*='@']", email);
        await page.fill('input[type=password]', pw);
        // Submit via Enter on the password field. The dev login renders a "Sign in"
        // TAB and a "Sign in" submit button; a text/role selector hits the tab (a no-op).
        await page.locator('input[type=password]').press('Enter');
        await page.waitForTimeout(4000);
        await page.waitForLoadState('domcontentloaded').catch(() => {});

        // Assert login actually succeeded (the robust check for both portals: the
        // password field is gone once authenticated).
        await expect(
          page.locator('input[type=password]'),
          `${portal} login should authenticate (password field should disappear)`,
        ).toHaveCount(0);
        expect(page.url(), `${portal} should leave the login page`).not.toMatch(/\/login(\b|\/|$)/);

        await use(page);
        await context.close();
      },
      { scope: 'worker' },
    ],
    recorder: [
      async ({ authedPage }, use) => {
        await use(new Recorder(authedPage));
      },
      { scope: 'worker' },
    ],
  });
}

export type AuthedTest = ReturnType<typeof makeAuthedTest>;

export { expect };
