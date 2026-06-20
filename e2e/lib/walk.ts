import type { Page } from '@playwright/test';

/**
 * Shared helpers for the portal walkthrough, ported from the original
 * exploratory crawler. The two discriminators that actually catch breakage are
 * (1) uncaught page errors and (2) HTTP responses >= 400 — everything else is
 * filtered as benign noise so the test gives a low-noise, honest signal.
 */

// Buttons we must NEVER click on a live shared environment (irreversible / session-ending).
export const DESTRUCTIVE =
  /delete|remove|revoke|rotate|suspend|deactivate|destroy|reset|purge|wipe|drop|disable|terminate|sign\s*out|log\s*out|leave/i;

// Asset/telemetry/HMR noise that is never a real failure.
const BENIGN_URL =
  /favicon|\/_next\/static|telemetry|hot-update|\.map($|\?)|\/__nextjs|sockjs/i;

// Known-benign console messages (documented, asserted-around — see docs/ops-runbook.md).
const BENIGN_CONSOLE = [
  // Radix UI accessibility advisory emitted at console.error level on any page with a Dialog.
  // Non-functional; tracked as a separate a11y cleanup, not a walkthrough failure.
  /DialogContent.*requires a `DialogTitle`/i,
  // Surfaced from a failed/blocked fetch we already classify via the response listener.
  /Failed to load resource/i,
];

/**
 * Endpoints that legitimately 4xx for the *test accounts* and are not bugs.
 * Documented so the signal stays honest. Keep this list tiny and justified.
 */
const KNOWN_BENIGN_RESPONSES: { pattern: RegExp; why: string }[] = [
  {
    // The dev test account is intentionally not a member of any team, so the
    // portal's "my teams" lookup 403s and the UI shows "No team assigned".
    pattern: /\/developers\/[0-9a-f-]+\/teams\b/i,
    why: 'dev test account has no team (UI handles gracefully)',
  },
];

export interface Captured {
  pageErrors: string[];
  failedResponses: string[];
  consoleErrors: string[];
}

/** Attaches listeners to a page and accumulates findings; reset() per route. */
export class Recorder {
  private data: Captured = { pageErrors: [], failedResponses: [], consoleErrors: [] };

  constructor(page: Page) {
    page.on('pageerror', (err) => this.data.pageErrors.push(String(err).slice(0, 300)));
    page.on('console', (msg) => {
      if (msg.type() !== 'error') return;
      const text = msg.text();
      if (BENIGN_CONSOLE.some((re) => re.test(text))) return;
      this.data.consoleErrors.push(text.slice(0, 300));
    });
    page.on('response', (res) => {
      const status = res.status();
      if (status < 400 || status === 401 || status === 429) return; // 401/429 = pre-auth / rate-limit noise
      const url = res.url();
      if (BENIGN_URL.test(url)) return;
      if (KNOWN_BENIGN_RESPONSES.some((k) => k.pattern.test(url))) return;
      this.data.failedResponses.push(`${status} ${res.request().method()} ${url.slice(0, 160)}`);
    });
    // Any native confirm()/alert() from a clicked button auto-cancels.
    page.on('dialog', (d) => d.dismiss().catch(() => {}));
  }

  reset(): void {
    this.data = { pageErrors: [], failedResponses: [], consoleErrors: [] };
  }

  snapshot(): Captured {
    return {
      pageErrors: [...this.data.pageErrors],
      failedResponses: [...this.data.failedResponses],
      consoleErrors: [...this.data.consoleErrors],
    };
  }
}

/** Let async work settle without using networkidle (the dashboard polls every 10s). */
export async function settle(page: Page, ms = 1200): Promise<void> {
  await page.waitForLoadState('domcontentloaded').catch(() => {});
  await page.waitForTimeout(ms);
}

/**
 * Click every visible, non-destructive button once (deduped by label), returning
 * to `path` if a click navigated away. Confirms buttons respond without firing
 * irreversible actions. Returns the labels clicked and (destructive) skipped.
 */
export async function clickSafeButtons(
  page: Page,
  path: string,
): Promise<{ clicked: string[]; skipped: string[] }> {
  const clicked: string[] = [];
  const skipped: string[] = [];
  const seen = new Set<string>();
  const buttons = await page.locator('button:visible, [role=button]:visible').all();
  for (const b of buttons) {
    let label = '';
    try {
      label = ((await b.innerText()) || '').trim().replace(/\s+/g, ' ').slice(0, 40);
    } catch {
      continue;
    }
    const key = label.toLowerCase();
    if (!label || seen.has(key)) continue;
    seen.add(key);
    if (DESTRUCTIVE.test(label)) {
      skipped.push(label);
      continue;
    }
    try {
      if (!(await b.isEnabled())) continue;
      await b.click({ timeout: 2500 });
      clicked.push(label);
      await page.waitForTimeout(400);
      await page.keyboard.press('Escape').catch(() => {}); // close any modal
      if (!page.url().includes(path)) {
        await page.goto(path).catch(() => {});
        await settle(page, 600);
      }
    } catch {
      // a non-clickable / detached button is not a failure for the walkthrough
    }
  }
  return { clicked, skipped };
}
