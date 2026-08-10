import { afterEach, expect, it, vi } from 'vitest';

import { api } from './client';

afterEach(() => vi.unstubAllGlobals());

it('exposes the audio UI client contract', () => {
  expect(typeof api.synthesizeHeyGenAudio).toBe('function');
  expect(typeof api.previewNarrationImport).toBe('function');
  expect(typeof api.commitNarrationImport).toBe('function');
});

it('preserves the server error code and recovery action for batch retry decisions', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            data: null,
            error: {
              code: 'heygen_timeout',
              message: 'HeyGen 请求超时',
              action: '系统将自动补跑失败页面',
            },
            request_id: 'request-timeout',
          }),
          { status: 422, headers: { 'Content-Type': 'application/json' } },
        ),
    ),
  );

  await expect(
    api.synthesizeHeyGenAudio('project-1', 'page-1', {
      profile_id: 'profile-1',
      revision_id: 'revision-1',
      voice_id: 'voice-1',
      speed: 1,
      replace_existing: false,
    }),
  ).rejects.toMatchObject({
    name: 'ApiRequestError',
    code: 'heygen_timeout',
    action: '系统将自动补跑失败页面',
    status: 422,
  });
});
