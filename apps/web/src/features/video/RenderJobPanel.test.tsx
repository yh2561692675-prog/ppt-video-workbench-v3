import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import type { RenderJob, RenderJobStatus } from '../../api/client';
import { RenderJobPanel } from './RenderJobPanel';

afterEach(() => vi.unstubAllGlobals());

const baseJob: RenderJob = {
  id: 'job-1',
  project_id: 'project-1',
  job_type: 'export_package',
  status: 'running',
  progress: 0.4,
  attempts: 1,
  max_attempts: 3,
  stage: 'rendering_pages',
  message: '第 2 页渲染完成',
  error: null,
  error_code: null,
  revision: 4,
  created_at: '2026-08-10T00:00:00Z',
  updated_at: '2026-08-10T00:01:00Z',
  heartbeat_at: '2026-08-10T00:01:00Z',
  started_at: '2026-08-10T00:00:01Z',
  finished_at: null,
  result: null,
};

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify({ data, error: null, request_id: 'request-1' }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <RenderJobPanel projectId="project-1" />
    </QueryClientProvider>,
  );
}

function installFetch(job: RenderJob | null, actionJob = job) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith('/video/render-jobs/current') && !init?.method) {
      return jsonResponse(job ? { job } : null);
    }
    if (url.endsWith('/video/render-jobs/job-1/actions')) {
      return jsonResponse({ job: actionJob, created: false });
    }
    if (url.endsWith('/video/render-jobs') && init?.method === 'POST') {
      return jsonResponse({ job: actionJob ?? baseJob, created: true }, 202);
    }
    throw new Error(`unexpected request ${url}`);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

it.each<[RenderJobStatus, string]>([
  ['queued', '排队中'],
  ['running', '渲染中'],
  ['pause_requested', '等待暂停'],
  ['paused', '已暂停'],
  ['cancel_requested', '等待取消'],
  ['succeeded', '已完成'],
  ['failed', '失败'],
  ['cancelled', '已取消'],
])('renders the %s state label', async (status, label) => {
  installFetch({ ...baseJob, status });
  renderPanel();
  expect(await screen.findByText(label)).toBeInTheDocument();
});

it('asks for confirmation before cancelling and preserves the cache message', async () => {
  const cancelRequested = { ...baseJob, status: 'cancel_requested' as const };
  const fetch = installFetch(baseJob, cancelRequested);
  renderPanel();

  fireEvent.click(await screen.findByRole('button', { name: '取消' }));
  expect(screen.getByRole('alertdialog')).toHaveTextContent('已验证的页面缓存会保留');
  fireEvent.click(screen.getByRole('button', { name: '确认取消' }));

  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      '/api/projects/project-1/video/render-jobs/job-1/actions',
      expect.objectContaining({ body: JSON.stringify({ action: 'cancel' }) }),
    ),
  );
});

it('shows terminal output paths and cached page count', async () => {
  const succeeded: RenderJob = {
    ...baseJob,
    status: 'succeeded',
    progress: 1,
    result: {
      mp4_relative_path: '08_输出/最终视频.mp4',
      package_relative_path: '08_输出/制作包-job-1',
      duration_ms: 2000,
      width: 1920,
      height: 1080,
      video_codec: 'h264',
      audio_codec: 'aac',
      artifact_count: 4,
      cached_pages: 2,
    },
  };
  installFetch(succeeded);
  renderPanel();

  expect(await screen.findByText(/最终视频\.mp4/)).toBeInTheDocument();
  expect(screen.getByText(/缓存页数：2/)).toBeInTheDocument();
});

it('offers retry for failed jobs', async () => {
  const failed = { ...baseJob, status: 'failed' as const, error_code: 'render_page_failed' };
  installFetch(failed);
  renderPanel();

  expect(await screen.findByRole('button', { name: '重试' })).toBeEnabled();
  expect(screen.getByText('错误代码：render_page_failed')).toBeInTheDocument();
});
