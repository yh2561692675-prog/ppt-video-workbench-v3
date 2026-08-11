import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import type { Project } from '../../api/client';
import { presenterApi } from './api';
import { PresenterModeEntry } from './PresenterModeEntry';
import { PresenterWorkspace } from './PresenterWorkspace';

afterEach(() => vi.restoreAllMocks());

const baseProject: Project = {
  schema_version: 1,
  id: 'project-1',
  name: 'demo',
  project_dir: 'demo',
  created_at: '2026-08-10T00:00:00Z',
  updated_at: '2026-08-10T00:00:00Z',
  current_step: 5,
  status: 'running',
  pages: [],
  jobs: [],
  source_files: [],
  audit_log: [],
  matches: [],
  presentation_mode: 'ai_narration',
};

it('does not load presenter endpoints in AI narration mode', () => {
  const spy = vi.spyOn(presenterApi, 'patchAnchor');
  render(<PresenterWorkspace project={baseProject} onChanged={() => undefined} />);
  expect(screen.queryByText('真人讲解')).not.toBeInTheDocument();
  expect(spy).not.toHaveBeenCalled();
});

it('keeps AI narration as default until a presenter source is explicitly imported', async () => {
  const importSource = vi.spyOn(presenterApi, 'importSource').mockResolvedValue({
    ...baseProject,
    presentation_mode: 'human_presenter',
  });
  const onChanged = vi.fn();
  render(<PresenterModeEntry projectId="project-1" onChanged={onChanged} />);
  const file = new File(['video'], 'presenter.mp4', { type: 'video/mp4' });

  fireEvent.change(screen.getByLabelText('选择用于启用真人模式的视频'), {
    target: { files: [file] },
  });
  fireEvent.click(screen.getByRole('button', { name: '启用真人讲解并导入' }));

  await waitFor(() => expect(importSource).toHaveBeenCalledWith('project-1', file));
  expect(onChanged).toHaveBeenCalledWith(
    expect.objectContaining({ presentation_mode: 'human_presenter' }),
  );
});

it('shows six review zones and sends expected revision when locking', async () => {
  const project: Project = {
    ...baseProject,
    presentation_mode: 'human_presenter',
    presenter_source: {
      id: 'source-1',
      relative_path: 'presenter/source.mp4',
      sha256: 'a'.repeat(64),
      duration_ms: 2000,
      media_type: 'video/mp4',
      probe_snapshot: {},
      imported_at: null,
    },
    presenter_timeline: {
      schema_version: '1.0',
      revision: 3,
      source_id: 'source-1',
      source_version: 'a'.repeat(64),
      duration_ms: 2000,
      anchors: [
        {
          page_id: 'page-1',
          start_ms: 0,
          end_ms: 2000,
          sentence_ids: ['s1'],
          confidence: 0.95,
          status: 'auto',
          manual_lock: false,
          source_revision: 'a'.repeat(64),
        },
      ],
      segments: [],
      unassigned_ranges: [],
      timeline_hash: 'b'.repeat(64),
      generated_at: null,
    },
  };
  const patch = vi.spyOn(presenterApi, 'patchAnchor').mockResolvedValue(project);
  render(<PresenterWorkspace project={project} onChanged={() => undefined} />);
  expect(screen.getByLabelText('真人源视频')).toBeInTheDocument();
  expect(screen.getByLabelText('识别文本')).toBeInTheDocument();
  expect(screen.getByLabelText('匹配复核')).toBeInTheDocument();
  expect(screen.getByLabelText('小窗样式')).toBeInTheDocument();
  expect(screen.getByLabelText('演讲者时间线')).toBeInTheDocument();
  expect(screen.getByLabelText('预览与核对')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '保存并锁定' }));
  await waitFor(() =>
    expect(patch).toHaveBeenCalledWith(
      'project-1',
      'page-1',
      expect.objectContaining({ expected_revision: 3 }),
    ),
  );
});
