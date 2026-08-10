import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ConfirmationPanel } from './ConfirmationPanel';

const pages = [
  {
    id: 'page-1',
    order: 1,
    title: '第一页',
    narration: {
      revision_id: 'revision-1',
      text: '第一页旁白。',
      version: 1,
      source_refs: [],
      status: 'needs_confirmation' as const,
    },
  },
  {
    id: 'page-2',
    order: 2,
    title: '第二页',
    narration: {
      revision_id: 'revision-2',
      text: '第二页旁白。',
      version: 1,
      source_refs: [],
      status: 'needs_confirmation' as const,
    },
  },
];

describe('narration confirmation panel', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows a batch summary, collects conflict handling, and exposes page jumps', async () => {
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/workflow/audio-gate') && (!init?.method || init.method === 'GET')) {
        return response({
          allowed: false,
          reasons: [
            {
              code: 'narration_unconfirmed',
              message: '当前旁白版本尚未确认',
              page_id: 'page-1',
              action: '请检查并确认当前版本',
            },
          ],
        });
      }
      return response([
        { id: 'confirmation-1', page_id: 'page-1' },
        { id: 'confirmation-2', page_id: 'page-2' },
      ]);
    });

    render(
      <QueryClientProvider client={queryClient}>
        <ConfirmationPanel
          projectId="project-1"
          pages={pages}
          conflictsByPage={{ 'page-1': ['课件写4年，大纲写5年'] }}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole('link', { name: '跳转到第一页' })).toHaveAttribute(
      'href',
      '#narration-page-page-1',
    );
    fireEvent.click(screen.getByRole('button', { name: '查看批量确认摘要' }));
    expect(screen.getByText('2 页待确认')).toBeInTheDocument();
    expect(screen.getByText('课件写4年，大纲写5年')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '确认全部当前版本' })).toBeDisabled();

    fireEvent.change(screen.getByLabelText('第一页冲突处理说明'), {
      target: { value: '并列保留两种说法。' },
    });
    fireEvent.click(screen.getByRole('button', { name: '确认全部当前版本' }));
    expect(await screen.findByText('已确认 2 页')).toBeInTheDocument();
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['project', 'project-1'] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ['narration-gate', 'project-1'] });
  });
});

function response(data: unknown) {
  return new Response(JSON.stringify({ data, error: null, request_id: 'request-1' }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
