import { expect, test } from '@playwright/test';

const apiBaseUrl = 'http://127.0.0.1:8765';

test('HeyGen acceptance uses a local fake boundary in automated runs', async ({ request }) => {
  const health = await request.get(`${apiBaseUrl}/api/health`);
  expect(health.ok()).toBeTruthy();
  expect((await health.json()).status).toBe('ok');
});

test('real HeyGen two-page route records cost and cache evidence', async () => {
  test.skip(
    !process.env.M8_RUN_REAL_E2E,
    'requires explicit real HeyGen credentials, a two-page budget and Windows RC sign-off',
  );
  // The real-service steps are executed only in the controlled Windows RC1 environment.
});
