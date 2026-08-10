import { fireEvent, render, screen } from '@testing-library/react';
import { expect, it, vi } from 'vitest';

import { PreviewWorkspace } from './PreviewWorkspace';

const pages = [
  { page_id: 'page-1', page_order: 1, title: '第一页', preview_path: 'preview-1.png' },
  { page_id: 'page-2', page_order: 2, title: '第二页', preview_path: 'preview-2.png' },
];

it('shows preflight blockers and keeps rendering unavailable', () => {
  render(
    <PreviewWorkspace
      projectId="project-1"
      pages={pages}
      preflight={{
        allowed: false,
        issues: [
          {
            code: 'subtitle_overlap',
            message: '第1页字幕与正文重叠',
            action: '调整字幕位置后重新预检',
            page_id: 'page-1',
            blocking: true,
          },
        ],
        placements: [],
      }}
      onPreflight={vi.fn()}
      onRender={vi.fn()}
    />,
  );

  expect(screen.getByText('完整预检未通过')).toBeInTheDocument();
  expect(screen.getByText('第1页字幕与正文重叠')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '开始渲染与导出' })).toBeDisabled();
});

it('allows preview controls and render after preflight passes', () => {
  const onRender = vi.fn();
  render(
    <PreviewWorkspace
      projectId="project-1"
      pages={pages}
      preflight={{ allowed: true, issues: [], placements: [] }}
      onPreflight={vi.fn()}
      onRender={onRender}
    />,
  );

  expect(screen.getByText('完整预检已通过')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '播放预览' })).toBeInTheDocument();
  const renderButton = screen.getByRole('button', { name: '开始渲染与导出' });
  expect(renderButton).toBeEnabled();
  fireEvent.click(renderButton);
  expect(onRender).toHaveBeenCalledTimes(1);
});

it('shows the effect plan revision and hash in the full preview', () => {
  render(
    <PreviewWorkspace
      projectId="project-1"
      pages={pages}
      preflight={{ allowed: true, issues: [], placements: [] }}
      onPreflight={vi.fn()}
      onRender={vi.fn()}
      effectPlanMeta={{ revision: 3, hash: 'abc123' }}
      effectControls={<div>effect controls</div>}
    />,
  );

  expect(screen.getByText(/EffectPlan revision 3/)).toBeInTheDocument();
  expect(screen.getByText('effect controls')).toBeInTheDocument();
});

it('embeds a Remotion player that its preview button controls', () => {
  const onPreflight = vi.fn();
  render(
    <PreviewWorkspace
      projectId="project-1"
      pages={pages}
      preflight={{
        allowed: true,
        issues: [],
        placements: [],
        props: {
          schema_version: 1,
          project_id: 'project-1',
          width: 1920,
          height: 1080,
          fps: 30,
          duration_ms: 2000,
          template_version: 'tech-board-v1',
          reduced_motion: false,
          pages: [
            {
              page_id: 'page-1',
              page_order: 1,
              title: '第一页',
              image_path: 'preview-1.png',
              audio_path: 'audio-1.wav',
              start_ms: 0,
              end_ms: 2000,
              subtitle_cue_ids: [],
            },
          ],
          subtitles: [],
          subtitle_placements: [],
        },
      }}
      onPreflight={onPreflight}
      onRender={vi.fn()}
    />,
  );

  expect(screen.getByTestId('remotion-player')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '播放预览' }));
  expect(screen.getByRole('button', { name: '暂停预览' })).toBeInTheDocument();
  fireEvent.click(screen.getByRole('checkbox', { name: '减少动态效果' }));
  expect(onPreflight).toHaveBeenLastCalledWith({ reduced_motion: true });
});
