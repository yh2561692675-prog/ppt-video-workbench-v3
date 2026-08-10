import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { AudioPipelineActions } from './AudioPipelineActions';

afterEach(() => vi.unstubAllGlobals());

it('exposes transcription, difference comparison and automatic paging in order', async () => {
  const requests: string[] = [];
  const bodies: unknown[] = [];
  const onChanged = vi.fn();
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    requests.push(url);
    bodies.push(init?.body ? JSON.parse(String(init.body)) : null);
    const data = url.endsWith('/transcription-devices')
      ? ['cpu', 'cuda']
      : url.endsWith('/transcribe')
        ? { segments: [], words: [], detected_language: 'zh', model: 'small', device: 'cpu' }
        : url.endsWith('/compare')
          ? []
          : {
              id: 'timeline',
              version: 1,
              duration_ms: 1000,
              min_page_ms: 300,
              boundaries: [],
              segments: [],
            };
    return new Response(JSON.stringify({ data, error: null, request_id: 'request' }), {
      headers: { 'Content-Type': 'application/json' },
    });
  });
  render(<AudioPipelineActions projectId="project-1" onChanged={onChanged} />);
  fireEvent.change(await screen.findByLabelText('转写设备'), { target: { value: 'cuda' } });
  fireEvent.click(screen.getByRole('button', { name: '转写本地录音' }));
  expect(await screen.findByText('本地转写已完成')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '检查旁白差异' }));
  expect(await screen.findByText('差异检查已完成')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '自动分页' }));
  expect(await screen.findByText('自动分页已完成')).toBeInTheDocument();
  expect(requests.map((url) => url.split('/').at(-1))).toEqual([
    'transcription-devices',
    'transcribe',
    'compare',
    'build',
  ]);
  expect(bodies[1]).toEqual({ device: 'cuda' });
  expect(onChanged).toHaveBeenCalledTimes(3);
});
