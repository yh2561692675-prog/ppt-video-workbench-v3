import { afterEach, expect, test, vi } from 'vitest';

import { api } from './client';

afterEach(() => {
  vi.unstubAllGlobals();
});

test('reports a readable server error when the response is plain text', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response('Internal Server Error', {
        status: 500,
        headers: { 'Content-Type': 'text/plain' },
      }),
    ),
  );

  await expect(api.previewHeyGenVoice('profile-1', 'voice-1', '测试')).rejects.toThrow(
    '服务端错误（HTTP 500）：Internal Server Error',
  );
});
