import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { NarrationEditor } from './NarrationEditor';

const page = {
  id: '00000000-0000-0000-0000-000000000011',
  order: 1,
  title: '专业概览',
  narration: {
    revision_id: '00000000-0000-0000-0000-000000000101',
    text: '第一版旁白。',
    version: 1,
    source_refs: ['page:1'],
    status: 'needs_confirmation' as const,
  },
};

describe('narration editor', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('edits, compares, and restores immutable page revisions', async () => {
    let version = 1;
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/settings/llm-profiles')) return response([]);
      if (!init?.method || init.method === 'GET') {
        return response([revision(1, '第一版旁白。', '00000000-0000-0000-0000-000000000101')]);
      }
      version += 1;
      const restored = url.includes('/restore/');
      return response(
        revision(
          version,
          restored ? '第一版旁白。' : '第二版旁白，包含更清楚的培养说明。',
          `00000000-0000-0000-0000-00000000010${version}`,
        ),
      );
    });

    render(
      <QueryClientProvider client={new QueryClient()}>
        <NarrationEditor
          projectId="00000000-0000-0000-0000-000000000001"
          page={page}
          pageText="课件原文：培养目标。"
          outlineText="大纲原文：专业概览。"
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('版本 1')).toBeInTheDocument();
    expect(screen.getByText('课件原文：培养目标。')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('旁白正文'), {
      target: { value: '第二版旁白，包含更清楚的培养说明。' },
    });
    expect(screen.getByText(/字数 17/)).toBeInTheDocument();
    expect(screen.getByText(/预计 4.3 秒/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '保存新版本' }));
    expect(await screen.findByText('版本 2')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '恢复版本 1' }));
    expect(await screen.findByText('版本 3')).toBeInTheDocument();
    expect(screen.getByLabelText('旁白正文')).toHaveValue('第一版旁白。');
  });

  it('generates a source-constrained draft with a saved profile', async () => {
    const queryClient = new QueryClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/settings/llm-profiles')) {
        return response([
          {
            id: '00000000-0000-0000-0000-000000000201',
            name: '本地兼容模型',
            base_url: 'https://llm.example.test/v1',
            base_url_digest: 'digest',
            model: 'compatible-model',
            has_api_key: true,
            created_at: '2026-08-03T00:00:00Z',
            updated_at: '2026-08-03T00:00:00Z',
            last_used_at: null,
          },
        ]);
      }
      if (url.endsWith('/generate') && init?.method === 'POST') {
        expect(JSON.parse(String(init.body))).toEqual({
          profile_id: '00000000-0000-0000-0000-000000000201',
        });
        return response(
          revision(2, '根据当前页与匹配大纲生成的旁白。', '00000000-0000-0000-0000-000000000102'),
        );
      }
      return response([revision(1, '第一版旁白。', '00000000-0000-0000-0000-000000000101')]);
    });

    render(
      <QueryClientProvider client={queryClient}>
        <NarrationEditor
          projectId="00000000-0000-0000-0000-000000000001"
          page={page}
          pageText="课件原文：培养目标。"
          outlineText="大纲原文：专业概览。"
        />
      </QueryClientProvider>,
    );

    expect(
      await screen.findByRole('option', { name: '本地兼容模型 · compatible-model' }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '生成 AI 草稿' }));
    expect(await screen.findByText('版本 2')).toBeInTheDocument();
    expect(screen.getByLabelText('旁白正文')).toHaveValue('根据当前页与匹配大纲生成的旁白。');
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: ['project', '00000000-0000-0000-0000-000000000001'],
    });
  });
});

function revision(version: number, text: string, id: string) {
  return {
    id,
    page_id: page.id,
    version,
    text,
    author: '规划师',
    source_refs: ['page:1'],
    insufficiencies: [],
    warnings: [],
    parent_revision_id: null,
    restored_from_revision_id: null,
    created_at: '2026-08-03T00:00:00Z',
    character_count: text.replaceAll(/\s/g, '').length,
    estimated_duration_seconds: text.replaceAll(/\s/g, '').length / 4,
  };
}

function response(data: unknown) {
  return new Response(JSON.stringify({ data, error: null, request_id: 'request-1' }), {
    headers: { 'Content-Type': 'application/json' },
  });
}
