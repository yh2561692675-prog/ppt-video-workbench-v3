import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { LlmSettings } from './LlmSettings';

describe('LLM settings', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('saves a secret profile without showing the key again and tests it', async () => {
    const requests: Array<{ url: string; body: string | undefined }> = [];
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      requests.push({ url, body: typeof init?.body === 'string' ? init.body : undefined });
      const data = url.endsWith('/test')
        ? { ok: true, profile_id: 'profile-1', model: 'compatible-model' }
        : {
            id: 'profile-1',
            name: '兼容接口',
            base_url: 'https://llm.example.test/v1',
            base_url_digest: 'abc123',
            model: 'compatible-model',
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
        <LlmSettings />
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByLabelText('配置名称'), { target: { value: '兼容接口' } });
    fireEvent.change(screen.getByLabelText('Base URL'), {
      target: { value: 'https://llm.example.test/v1' },
    });
    fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'sk-ui-secret' } });
    fireEvent.change(screen.getByLabelText('模型名称'), {
      target: { value: 'compatible-model' },
    });
    fireEvent.click(screen.getByRole('button', { name: '安全保存配置' }));

    expect(await screen.findByText('密钥已由本机安全保护')).toBeInTheDocument();
    expect(screen.getByLabelText('API Key')).toHaveValue('');
    expect(screen.queryByDisplayValue('sk-ui-secret')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '测试连接' }));
    expect(await screen.findByText('连接成功')).toBeInTheDocument();
    expect(requests).toHaveLength(2);
  });
});
