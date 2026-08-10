import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { UpdatePanel } from './UpdatePanel';

describe('update panel', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('requires confirmation before applying a staged stable update', async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      'confirm',
      vi.fn(() => true),
    );
    vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
      const url = String(input);
      calls.push(url);
      const data = url.endsWith('/check')
        ? {
            version: '1.1.0',
            channel: 'stable',
            notes: '修复稳定性问题',
            size: 2048,
            sha256: 'a'.repeat(64),
            package_relative_path: 'updates/1.1.0',
          }
        : url.endsWith('/stage')
          ? {
              current_version: '1.0.0',
              previous_version: null,
              staged_version: '1.1.0',
              status: 'staged',
              updated_at: '2026-08-04T00:00:00Z',
            }
          : url.endsWith('/apply')
            ? {
                current_version: '1.1.0',
                previous_version: '1.0.0',
                staged_version: null,
                status: 'applied',
                updated_at: '2026-08-04T00:00:00Z',
              }
            : {
                current_version: '1.0.0',
                previous_version: null,
                staged_version: null,
                status: 'idle',
                updated_at: null,
              };
      return new Response(JSON.stringify({ data, error: null, request_id: 'request-1' }), {
        headers: { 'Content-Type': 'application/json' },
      });
    });

    render(
      <QueryClientProvider client={new QueryClient()}>
        <UpdatePanel />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('可用 stable 更新：1.1.0')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '下载并暂存' }));
    expect(await screen.findByRole('button', { name: '确认应用更新' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '确认应用更新' }));
    expect(await screen.findByText('已应用 1.1.0')).toBeInTheDocument();
    expect(window.confirm).toHaveBeenCalledTimes(1);
    expect(calls).toContain('/api/updates/check');
    expect(calls).toContain('/api/updates/stage');
    expect(calls).toContain('/api/updates/apply');
  });
});
