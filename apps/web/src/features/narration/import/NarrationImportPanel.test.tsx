import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { NarrationImportPanel } from './NarrationImportPanel';

describe('narration import panel', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('previews assignments before writing unconfirmed drafts', async () => {
    const mockedFetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/preview')) {
        return response({
          source_name: '旁白稿.txt',
          assignments: [
            {
              page_id: 'page-1',
              page_order: 1,
              page_title: '专业概览',
              text: '第一页旁白。',
              method: 'page_number',
              warning: null,
            },
          ],
        });
      }
      expect(JSON.parse(String(init?.body))).toMatchObject({
        assignments: [
          {
            page_id: 'page-1',
            text: '第一页旁白。',
            expected_revision_id: null,
          },
        ],
      });
      return response([{ page_id: 'page-1', version: 1 }]);
    });
    vi.stubGlobal('fetch', mockedFetch);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <NarrationImportPanel
          projectId="project-1"
          pages={[{ id: 'page-1', order: 1, title: '专业概览', narration: null }]}
        />
      </QueryClientProvider>,
    );

    fireEvent.change(screen.getByLabelText('上传旁白稿'), {
      target: {
        files: [
          new File(['第1页\\n第一页旁白。'], '旁白稿.txt', {
            type: 'text/plain',
          }),
        ],
      },
    });
    fireEvent.click(screen.getByRole('button', { name: '解析并生成逐页预览' }));

    expect(await screen.findByDisplayValue('第一页旁白。')).toBeInTheDocument();
    expect(mockedFetch).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: '写入 1 页草稿' }));
    expect(await screen.findByText('已写入 1 页旁白草稿，仍需逐页确认。')).toBeInTheDocument();
  });
});

function response(data: unknown) {
  return new Response(JSON.stringify({ data, error: null, request_id: 'request-1' }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
