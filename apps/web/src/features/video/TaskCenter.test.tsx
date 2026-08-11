import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { api } from '../../api/client';
import { TaskCenter } from './TaskCenter';

describe('TaskCenter', () => {
  it('lists durable jobs and sends revision-guarded actions', async () => {
    vi.spyOn(api, 'listDurableJobs').mockResolvedValue([
      {
        schema_version: '1.0',
        id: 'job-1',
        project_id: 'project-1',
        job_type: 'render_preview',
        status: 'running',
        cache_key: 'preview:project-1',
        page_id: null,
        progress: 0.4,
        attempts: 1,
        max_attempts: 3,
        paid: false,
        input_fingerprint: null,
        idempotency_key: null,
        parent_job_id: null,
        payload: {},
        stage: 'rendering',
        message: 'working',
        error: null,
        error_code: null,
        revision: 7,
        priority: 0,
        current_attempt_id: 'attempt-1',
        created_at: '',
        updated_at: '',
        heartbeat_at: null,
        started_at: null,
        finished_at: null,
        result: null,
      },
    ]);
    const act = vi.spyOn(api, 'actDurableJob').mockImplementation(async (_id, _jobId, input) => ({
      ...(await api.listDurableJobs('project-1'))[0],
      status: 'paused',
      revision: input.expected_revision + 1,
    }));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <TaskCenter projectId="project-1" />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('render_preview')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '暂停' }));
    await waitFor(() =>
      expect(act).toHaveBeenCalledWith('project-1', 'job-1', {
        action: 'pause',
        expected_revision: 7,
      }),
    );
  });
});
