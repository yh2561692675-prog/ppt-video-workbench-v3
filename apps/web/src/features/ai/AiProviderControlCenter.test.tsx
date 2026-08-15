import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AiProviderControlCenter } from './AiProviderControlCenter';

describe('AiProviderControlCenter', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('keeps the provider control plane off while showing local capabilities', async () => {
    const calls: string[] = [];
    vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      const body = url.endsWith('/ai/models')
        ? []
        : url.endsWith('/ai/voices')
          ? []
          : url.endsWith('/ai/content-assist')
            ? [
                {
                  candidate_id: 'candidate-1',
                  request_id: 'request-1',
                  kind: 'polish',
                  status: 'candidate',
                  source_text: '原文',
                  candidate_text: '润色后的候选',
                  source_language: 'zh-CN',
                  target_language: null,
                  segments: [],
                  provider_id: null,
                  warnings: [],
                  created_at: '2026-08-15T00:00:00Z',
                  accepted_at: null,
                },
              ]
            : [];
      return new Response(JSON.stringify({ data: body, error: null, request_id: 'test' }), {
        headers: { 'Content-Type': 'application/json' },
      });
    });

    render(
      <QueryClientProvider client={new QueryClient()}>
        <AiProviderControlCenter />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('本地生产链：可独立运行')).toBeInTheDocument();
    expect(await screen.findByText('润色后的候选')).toBeInTheDocument();
    expect(screen.getByText('默认关闭')).toBeInTheDocument();
    expect(calls.some((url) => url.endsWith('/api/providers'))).toBe(false);

    fireEvent.click(screen.getByRole('checkbox', { name: /启用 AI \/ Provider 控制面/ }));
    expect(await screen.findByText('等待显式 Provider')).toBeInTheDocument();
    expect(calls.some((url) => url.endsWith('/api/providers'))).toBe(true);
  });
});
