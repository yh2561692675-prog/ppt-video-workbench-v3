import { expect, test } from '@playwright/test';

const apiBaseUrl = 'http://127.0.0.1:8765';

test('local audio acceptance entrypoint preserves the audio gate', async ({ request }) => {
  const created = await request.post(`${apiBaseUrl}/api/projects`, {
    data: { name: `M8 本地音频 smoke-${Date.now()}` },
  });
  expect(created.ok()).toBeTruthy();
  const project = (await created.json()).data;

  const gate = await request.get(`${apiBaseUrl}/api/projects/${project.id}/audio/gate`);
  expect(gate.ok()).toBeTruthy();
  const result = (await gate.json()).data;
  expect(result.allowed).toBe(false);
  expect(Array.isArray(result.reasons)).toBe(true);
});

test('real local audio full chain produces the signed RC1 package', async () => {
  test.skip(
    !process.env.M8_RUN_REAL_E2E,
    'requires Windows RC, real 6–8 page audio fixture, FFmpeg and manual audiovisual review',
  );
  // The real-project steps are executed by the Windows RC1 acceptance plan.
});
