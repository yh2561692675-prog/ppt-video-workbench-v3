import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { AudioDifferences } from './AudioDifferences';

afterEach(() => vi.unstubAllGlobals());

it('locates a difference and records the selected manual resolution', async () => {
  const onChanged = vi.fn();
  const difference = {
    id: 'difference-1',
    page_id: 'page-1',
    kind: 'misread' as const,
    expected: '培养目标',
    actual: '就业目标',
    start_ms: 1200,
    end_ms: 1800,
    confidence: 0.72,
    status: 'pending' as const,
    resolution: null,
    resolved_at: null,
  };
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            data: { ...difference, status: 'resolved', resolution: 'accept_recording' },
            error: null,
            request_id: 'request-1',
          }),
          { headers: { 'Content-Type': 'application/json' } },
        ),
    ),
  );

  render(
    <AudioDifferences projectId="project-1" differences={[difference]} onChanged={onChanged} />,
  );
  expect(screen.getByText('00:01.200')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: '接受录音' }));
  expect(await screen.findByText('已处理：接受录音')).toBeInTheDocument();
  expect(onChanged).toHaveBeenCalledTimes(1);
});

it('shows fresh differences when the authoritative project is reloaded', () => {
  const { rerender } = render(<AudioDifferences projectId="project-1" differences={[]} />);
  rerender(
    <AudioDifferences
      projectId="project-1"
      differences={[
        {
          id: 'difference-new',
          page_id: 'page-1',
          kind: 'omission',
          expected: '刷新后的差异',
          actual: '',
          start_ms: 2000,
          end_ms: 2500,
          confidence: 0.8,
          status: 'pending',
          resolution: null,
          resolved_at: null,
        },
      ]}
    />,
  );

  expect(screen.getByText('原文：刷新后的差异')).toBeInTheDocument();
});
