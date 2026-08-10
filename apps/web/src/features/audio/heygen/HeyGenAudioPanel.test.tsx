import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { NarrationPage } from '../../../api/client';
import { HeyGenAudioPanel } from './HeyGenAudioPanel';

afterEach(() => vi.unstubAllGlobals());

const pages: NarrationPage[] = [1, 2, 3].map((order) => ({
  id: `page-${order}`,
  order,
  title: `页面${order}`,
  narration: {
    revision_id: `revision-${order}`,
    text: `第${order}页旁白`,
    version: 1,
    source_refs: [],
    status: 'completed',
  },
}));

function envelope(data: unknown, status = 200) {
  return new Response(JSON.stringify({ data, error: null, request_id: 'request-ok' }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function timeoutEnvelope() {
  return new Response(
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
  );
}

function installFetch(alwaysFailPages: ReadonlySet<string> = new Set()) {
  const calls: string[] = [];
  let pageTwoAttempts = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url === '/api/settings/heygen-profiles') {
        return envelope([
          {
            id: 'profile-1',
            name: 'Video',
            base_url: 'https://api.heygen.com',
            base_url_digest: 'digest',
            has_api_key: true,
            created_at: '2026-08-09T00:00:00Z',
            updated_at: '2026-08-09T00:00:00Z',
            last_used_at: null,
          },
        ]);
      }
      if (url === '/api/settings/heygen-profiles/profile-1/voices') {
        return envelope([
          {
            voice_id: 'voice-1',
            name: '本人声音',
            language: 'Chinese',
            gender: 'male',
            support_pause: true,
            support_locale: true,
            preview_audio_url: null,
          },
        ]);
      }
      const match = url.match(/\/audio\/heygen\/(page-\d)$/);
      if (match && init?.method === 'POST') {
        calls.push(match[1]);
        if (alwaysFailPages.has(match[1])) return timeoutEnvelope();
        if (match[1] === 'page-2') {
          pageTwoAttempts += 1;
          if (pageTwoAttempts < 3) return timeoutEnvelope();
        }
        return envelope(
          {
            page_id: match[1],
            relative_path: `05_音频/HeyGen/${match[1]}.wav`,
            duration_ms: 1000,
            source: 'heygen',
            cache_key: `cache-${match[1]}`,
            voice_id: 'voice-1',
            request_id: `request-${match[1]}`,
            cached: false,
          },
          201,
        );
      }
      throw new Error(`unexpected request ${url}`);
    }),
  );
  return calls;
}

async function selectVoiceAndStart() {
  fireEvent.change(await screen.findByLabelText('HeyGen 配置'), {
    target: { value: 'profile-1' },
  });
  await screen.findByRole('option', { name: '本人声音（Chinese）' });
  fireEvent.change(screen.getByLabelText('声音'), { target: { value: 'voice-1' } });
  fireEvent.click(screen.getByRole('button', { name: '使用 HeyGen 生成全部页面配音' }));
}

it('continues later pages and automatically replays only a transiently failed page', async () => {
  const calls = installFetch();
  render(
    <HeyGenAudioPanel
      projectId="project-1"
      pages={pages}
      localAudioActive={false}
      isLocalAudioActive={() => false}
      onStarted={() => true}
      onChanged={() => undefined}
    />,
  );

  await selectVoiceAndStart();

  expect(await screen.findByText('全部 3 页 HeyGen 配音已生成。')).toBeInTheDocument();
  await waitFor(() => expect(calls).toEqual(['page-1', 'page-2', 'page-3', 'page-2', 'page-2']));
  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});

it('reports all pages once after the bounded replay passes are exhausted', async () => {
  const calls = installFetch(new Set(['page-2', 'page-3']));
  render(
    <HeyGenAudioPanel
      projectId="project-1"
      pages={pages}
      localAudioActive={false}
      isLocalAudioActive={() => false}
      onStarted={() => true}
      onChanged={() => undefined}
    />,
  );

  await selectVoiceAndStart();

  const alerts = await screen.findAllByRole('alert');
  expect(alerts).toHaveLength(1);
  expect(alerts[0]).toHaveTextContent('自动补跑 3 轮后仍有 2 页未完成');
  expect(alerts[0]).toHaveTextContent('第 2 页“页面2”');
  expect(alerts[0]).toHaveTextContent('第 3 页“页面3”');
  expect(calls).toEqual(['page-1', 'page-2', 'page-3', 'page-2', 'page-3', 'page-2', 'page-3']);
});
