import { expect } from '@playwright/test';
import { clickSafeButtons, settle } from './walk';
import type { AuthedTest } from '../fixtures/auth';

export interface Route {
  label: string;
  path: string;
}

/**
 * Generates one test per route on the shared authenticated page. Each route asserts:
 *  - navigation status < 400,
 *  - no uncaught page errors on load (catches client-side crashes like `x.map is not a function`),
 *  - no failed HTTP responses >= 400 on load (catches data that never loads, e.g. CSP-blocked
 *    or mis-routed fetches), filtered for benign noise (see lib/walk.ts),
 *  - then clicks every visible non-destructive button and re-checks for page errors.
 * Destructive buttons are recorded as a test annotation, never clicked.
 */
export function defineRouteSuite(test: AuthedTest, routes: Route[]): void {
  for (const route of routes) {
    test(`${route.label} — ${route.path}`, async ({ authedPage, recorder }) => {
      recorder.reset();

      const resp = await authedPage.goto(route.path, { waitUntil: 'domcontentloaded' });
      expect(resp?.status() ?? 0, 'navigation status').toBeLessThan(400);
      await settle(authedPage, 1500);

      const onLoad = recorder.snapshot();
      expect(onLoad.pageErrors, 'uncaught page errors on load').toEqual([]);
      expect(onLoad.failedResponses, 'failed HTTP responses on load').toEqual([]);

      const { clicked, skipped } = await clickSafeButtons(authedPage, route.path);

      const afterClicks = recorder.snapshot();
      expect(afterClicks.pageErrors, 'uncaught page errors after clicking buttons').toEqual([]);

      test.info().annotations.push(
        { type: 'buttons-clicked', description: `${clicked.length}` },
        { type: 'destructive-skipped', description: skipped.join(', ') || '(none)' },
      );
    });
  }
}
