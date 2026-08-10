import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PageMatch } from '../../api/client';
import { MatchingWorkspace } from './MatchingWorkspace';

const match: PageMatch = {
  page_id: 'page-1',
  page_order: 1,
  page_title: '课程体系',
  page_text: '课程体系\n机器学习',
  preview_path: null,
  selected_outline_ref: 'paragraph:1',
  score: 0.52,
  needs_confirmation: true,
  conflicts: ['title_conflict'],
  decision_source: 'deterministic_rules',
  candidates: [
    {
      outline_ref: 'paragraph:1',
      outline_title: '专业概览',
      outline_text: '专业概览\n培养目标',
      score: 0.52,
      weights: { page_order: 0.2, title: 0.45, keywords: 0.25, body: 0.1 },
      components: { page_order: 1, title: 0.1, keywords: 0.2, body: 0.1 },
    },
    {
      outline_ref: 'paragraph:2',
      outline_title: '课程体系',
      outline_text: '课程体系\n机器学习',
      score: 0.92,
      weights: { page_order: 0.2, title: 0.45, keywords: 0.25, body: 0.1 },
      components: { page_order: 0.5, title: 1, keywords: 1, body: 1 },
    },
  ],
};

describe('matching workspace', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows page evidence, scores and saves a reasoned manual override', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              data: {
                ...match,
                selected_outline_ref: 'paragraph:2',
                needs_confirmation: false,
                decision_source: 'manual',
              },
              error: null,
              request_id: 'request-1',
            }),
            { headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    );
    render(<MatchingWorkspace projectId="project-1" initialMatches={[match]} />);

    expect(
      screen.getByText(
        (_, element) => element?.tagName === 'PRE' && element.textContent === '课程体系\n机器学习',
      ),
    ).toBeInTheDocument();
    expect(screen.getByText('标题矛盾')).toBeInTheDocument();
    expect(screen.getByText('92%')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('大纲候选'), { target: { value: 'paragraph:2' } });
    fireEvent.change(screen.getByLabelText('改绑原因'), { target: { value: '人工核对标题一致' } });
    fireEvent.click(screen.getByRole('button', { name: '保存人工匹配' }));

    expect(await screen.findByText('人工匹配已保存')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it('starts material parsing and opens the persisted match result', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              data: { cached: false, cache_key: 'cache-1', pages: [], matches: [match] },
              error: null,
              request_id: 'request-2',
            }),
            { headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    );
    render(<MatchingWorkspace projectId="project-1" initialMatches={[]} />);

    fireEvent.click(screen.getByRole('button', { name: '开始解析与匹配' }));

    expect(await screen.findByText('材料解析完成')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '课程体系' })).toBeInTheDocument();
  });
});
