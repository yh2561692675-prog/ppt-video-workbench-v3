import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { api, type RenderGraphV2Record } from '../../api/client';
import { AuthoritativePreviewPanel } from './AuthoritativePreviewPanel';

const graph = {
  schema_version: '2.0',
  graph_id: '11111111-1111-4111-8111-111111111111',
  project_id: '22222222-2222-4222-8222-222222222222',
  timeline_revision: 7,
  timeline_hash: 'a'.repeat(64),
  compiler_version: 'test',
  duration_us: 20_000_000,
  canvas: { width: 1920, height: 1080, fps: 30 },
  nodes: [],
  transitions: [],
  assets: [],
  audio: { tracks: [] },
  subtitles: { render_mode: 'both', tracks: [] },
  source_revisions: {},
  affected_ranges: [],
  graph_hash: 'b'.repeat(64),
} as unknown as RenderGraphV2Record;

afterEach(() => vi.restoreAllMocks());

it('submits a frozen graph and microsecond range to the durable preview worker', async () => {
  const submit = vi.spyOn(api, 'createAuthoritativePreview').mockResolvedValue({
    id: 'job-1',
  } as never);
  vi.spyOn(api, 'getDurableJob').mockImplementation(() => new Promise(() => undefined));
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(
    <QueryClientProvider client={queryClient}>
      <AuthoritativePreviewPanel projectId={graph.project_id} graph={graph} />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText('权威预览开始时间'), { target: { value: '2.5' } });
  fireEvent.change(screen.getByLabelText('权威预览结束时间'), { target: { value: '8' } });
  fireEvent.click(screen.getByRole('button', { name: '生成权威预览' }));

  await waitFor(() =>
    expect(submit).toHaveBeenCalledWith(graph.project_id, graph.graph_id, {
      graph_id: graph.graph_id,
      graph_hash: graph.graph_hash,
      start_us: 2_500_000,
      end_us: 8_000_000,
      runtime_version: 'rendergraph-v2',
    }),
  );
});

it('blocks an invalid or out-of-bounds range before submission', () => {
  const submit = vi.spyOn(api, 'createAuthoritativePreview');
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

  render(
    <QueryClientProvider client={queryClient}>
      <AuthoritativePreviewPanel projectId={graph.project_id} graph={graph} />
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText('权威预览结束时间'), { target: { value: '21' } });

  expect(screen.getByRole('button', { name: '生成权威预览' })).toBeDisabled();
  expect(screen.getByText(/不能超出成片/)).toBeInTheDocument();
  expect(submit).not.toHaveBeenCalled();
});
