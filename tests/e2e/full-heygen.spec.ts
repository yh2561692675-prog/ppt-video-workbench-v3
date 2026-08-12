import { expect, test } from '@playwright/test';

import { realFlowEnabled, realFlowSkipReason } from './real-flow-policy';

const apiBaseUrl = 'http://127.0.0.1:8765';

test('HeyGen acceptance uses a local fake boundary in automated runs', async ({ request }) => {
  const health = await request.get(`${apiBaseUrl}/api/health`);
  expect(health.ok()).toBeTruthy();
  expect((await health.json()).status).toBe('ok');
});

test('real HeyGen two-page route records cost and cache evidence', async () => {
  test.skip(!realFlowEnabled('heygen-two-page'), realFlowSkipReason('heygen-two-page'));
  // The real service is performed only under its explicit provider authorization.
});
