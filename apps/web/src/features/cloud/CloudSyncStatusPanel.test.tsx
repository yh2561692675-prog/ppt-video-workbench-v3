import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CloudSyncStatusPanel } from './CloudSyncStatusPanel';

describe('CloudSyncStatusPanel', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('keeps the local-first state visible when sync is disabled', async () => {
    vi.stubGlobal(
      'fetch',
      async () =>
        new Response(
          JSON.stringify({
            schema_version: 1,
            generated_at: '2026-08-11T00:00:00Z',
            flags: { cloud_sync_enabled: false },
            platform: null,
            platform_details: null,
            providers: [],
            sync: null,
          }),
          { headers: { 'Content-Type': 'application/json' } },
        ),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <CloudSyncStatusPanel />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('当前为本地模式，未创建同步数据库。')).toBeInTheDocument();
  });
});
