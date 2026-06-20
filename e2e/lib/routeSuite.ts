import { expect } from '@playwright/test';
import { clickSafeButtons, settle } from './walk';
import type { AuthedTest } from '../fixtures/auth';

export interface Route {
  label: string;
  path: string;
}

// Button-clicking is the slow part against a remote env, and the core signal
// (route loads, no crash, no failed call) doesn't need it. Off by default; set
// E2E_CLICK=1 for the thorough "click every safe button" pass.
const CLICK = process.env.E2E_CLICK === '1';

/**
 * Generates one test per route on the shared authenticated page. Each route asserts:
 *  - navigation status < 400,
 *  - no uncaught page errors on load (catches client-side crashes like `x.map is not a function`),
 *  - no failed HTTP responses >= 400 on load (catches data that never loads, e.g. CSP-blocked
 *    or mis-routed fetches), filtered for benign noise (see lib/walk.ts).
 * With E2E_CLICK=1 it also clicks visible non-destructive buttons and re-checks
 * for page errors (destructive buttons are recorded, never clicked).
 */
export function defineRouteSuite(test: AuthedTest, routes: Route[]): void {
  for (const route of routes) {
    test(`${route.label} — ${route.path}`, async ({ authedPage, recorder }) => {
      recorder.reset();

      const resp = await authedPage.goto(route.path, { waitUntil: 'domcontentloaded' });
      expect(resp?.status() ?? 0, 'navigation status').toBeLessThan(400);
      await settle(authedPage, 600);

      const onLoad = recorder.snapshot();
      expect(onLoad.pageErrors, 'uncaught page errors on load').toEqual([]);
      expect(onLoad.failedResponses, 'failed HTTP responses on load').toEqual([]);

      if (CLICK) {
        const { clicked, skipped } = await clickSafeButtons(authedPage, route.path);
        expect(recorder.snapshot().pageErrors, 'page errors after clicking buttons').toEqual([]);
        test.info().annotations.push(
          { type: 'buttons-clicked', description: `${clicked.length}` },
          { type: 'destructive-skipped', description: skipped.join(', ') || '(none)' },
        );
      }
    });
  }
}
