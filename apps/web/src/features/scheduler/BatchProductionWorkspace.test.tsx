import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { BatchProductionRecord } from '../../api/client';
import { BatchProductionWorkspace } from './BatchProductionWorkspace';

const batch: BatchProductionRecord = {
  version: 1,
  revision: 2,
  batch_id: 'batch-12345678',
  project_id: 'project-1',
  created_at: '2026-08-11T00:00:00Z',
  status: 'running',
  night_queue: false,
  resource_limits: {
    max_parallel: 2,
    cpu_cores: 8,
    memory_mb: 16384,
    gpu_slots: 1,
    per_job_memory_mb: 4096,
  },
  content_hash: 'a'.repeat(64),
  items: [
    {
      item_id: 'item-1',
      preset_id: 'master-1080p-30',
      page_id: null,
      priority: 60,
      dependencies: [],
      resource_cpu: 1,
      resource_memory_mb: 2048,
      resource_gpu: 0,
      status: 'dispatched',
      job_id: 'job-1',
      attempts: 1,
      error: null,
    },
  ],
};

describe('BatchProductionWorkspace', () => {
  it('creates a night batch and dispatches the latest batch', () => {
    const onCreate = vi.fn();
    const onDispatch = vi.fn();
    render(
      <BatchProductionWorkspace
        batches={[batch]}
        presetIds={['master-1080p-30']}
        onCreate={onCreate}
        onDispatch={onDispatch}
        onRerun={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByLabelText('夜间队列'));
    fireEvent.click(screen.getByRole('button', { name: '创建批次' }));
    expect(onCreate).toHaveBeenCalledWith(expect.objectContaining({ night_queue: true }));
    fireEvent.click(screen.getByRole('button', { name: '调度可运行任务' }));
    expect(onDispatch).toHaveBeenCalledWith('batch-12345678', true);
  });
});
