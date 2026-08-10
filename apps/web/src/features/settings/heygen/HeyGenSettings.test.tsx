import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { HeyGenSettings } from './HeyGenSettings';

afterEach(() => vi.unstubAllGlobals());

it('saves the key securely, lists private voices and previews the selected voice', async () => {
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    const data =
      url.endsWith('/heygen-profiles') && method === 'GET'
        ? []
        : url.endsWith('/voices')
          ? [
              {
                voice_id: 'my-voice',
                name: '本人声音',
                language: 'Chinese',
                gender: 'male',
                support_pause: true,
                support_locale: true,
                preview_audio_url: 'https://files.example/voice.mp3',
              },
            ]
          : url.endsWith('/preview')
            ? {
                request_id: 'preview-1',
                audio_url: 'https://files.example/generated.mp3',
                duration: 1.2,
              }
            : {
                id: 'profile-1',
                name: 'HeyGen配置',
                base_url: 'https://api.heygen.com',
                base_url_digest: 'digest',
                has_api_key: true,
                created_at: '2026-08-03T00:00:00Z',
                updated_at: '2026-08-03T00:00:00Z',
                last_used_at: null,
              };
    return new Response(JSON.stringify({ data, error: null, request_id: 'request-1' }), {
      headers: { 'Content-Type': 'application/json' },
    });
  });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <HeyGenSettings />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText('配置名称'), { target: { value: 'HeyGen配置' } });
  fireEvent.change(screen.getByLabelText('HeyGen API Key'), { target: { value: 'hg-ui-secret' } });
  fireEvent.click(screen.getByRole('button', { name: '安全保存 HeyGen 配置' }));

  expect(await screen.findByRole('option', { name: '本人声音' })).toBeInTheDocument();
  expect(screen.getByLabelText('HeyGen API Key')).toHaveValue('');
  expect(screen.getByRole('status')).toHaveTextContent('连接成功，密钥已由本机安全保护');
  fireEvent.click(screen.getByRole('button', { name: '试听测试句' }));
  expect(await screen.findByText('试听已生成')).toBeInTheDocument();
});

it('updates an existing HeyGen profile instead of creating a duplicate', async () => {
  const existingProfile = {
    id: 'profile-existing',
    name: '已有配置',
    base_url: 'https://api.heygen.com',
    base_url_digest: 'digest',
    has_api_key: true,
    created_at: '2026-08-03T00:00:00Z',
    updated_at: '2026-08-03T00:00:00Z',
    last_used_at: null,
  };
  const requests: Array<{ url: string; method: string }> = [];
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    requests.push({ url, method });
    const data =
      url.endsWith('/heygen-profiles') && method === 'GET'
        ? [existingProfile]
        : url.endsWith('/voices')
          ? [{ voice_id: 'my-voice', name: '本人声音', language: 'Chinese', gender: 'male' }]
          : existingProfile;
    return new Response(JSON.stringify({ data, error: null, request_id: 'request-1' }), {
      headers: { 'Content-Type': 'application/json' },
    });
  });

  render(
    <QueryClientProvider client={new QueryClient()}>
      <HeyGenSettings />
    </QueryClientProvider>,
  );

  expect(await screen.findByRole('option', { name: '已有配置' })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('HeyGen API Key'), { target: { value: 'hg-new-secret' } });
  fireEvent.click(screen.getByRole('button', { name: '更新 HeyGen 配置' }));

  expect(await screen.findByText('连接成功，密钥已由本机安全保护')).toBeInTheDocument();
  expect(requests).toContainEqual({
    url: '/api/settings/heygen-profiles/profile-existing',
    method: 'PATCH',
  });
  expect(requests).not.toContainEqual({ url: '/api/settings/heygen-profiles', method: 'POST' });
});
