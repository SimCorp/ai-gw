import { makeAuthedTest } from '../fixtures/auth';
import { defineRouteSuite } from '../lib/routeSuite';

/**
 * Developer portal walkthrough. Routes are an explicit, reviewed list (the nav
 * surface confirmed by the exploratory crawl) so coverage is deterministic.
 * Next.js basePath is `/portal`, and the app's home is `/portal/portal`.
 */
const test = makeAuthedTest('dev');
const B = '/portal/portal';

test.describe('dev portal', () => {
  defineRouteSuite(test, [
    { label: 'home', path: `${B}` },
    { label: 'docs', path: `${B}/docs` },
    { label: 'keys', path: `${B}/keys` },
    { label: 'league', path: `${B}/league` },
    { label: 'library', path: `${B}/library` },
    { label: 'playground', path: `${B}/playground` },
    { label: 'settings', path: `${B}/settings` },
    { label: 'transformation', path: `${B}/transformation` },
    { label: 'usage', path: `${B}/usage` },
  ]);
});
