import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { AudioImport } from './AudioImport';

afterEach(() => vi.unstubAllGlobals());

it('imports a recording and shows its normalization quality warning', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            data: {
              id: 'audio-1',
              original_relative_path: '05_音频/原始录音/本人录音.mp3',
              normalized_relative_path: '05_音频/本人录音.normalized.wav',
              duration_ms: 1200,
              sample_rate: 16000,
              channels: 1,
              sha256: 'a'.repeat(64),
              peak_dbfs: -96,
              silence_ratio: 1,
              silence_intervals_ms: [[0, 1200]],
              needs_confirmation: true,
              imported_at: '2026-08-03T00:00:00Z',
            },
            error: null,
            request_id: 'request-1',
          }),
          { headers: { 'Content-Type': 'application/json' } },
        ),
    ),
  );
  render(<AudioImport projectId="project-1" initialAudio={null} />);

  fireEvent.change(screen.getByLabelText('选择本地录音'), {
    target: { files: [new File(['audio'], '本人录音.mp3', { type: 'audio/mpeg' })] },
  });
  fireEvent.click(screen.getByRole('button', { name: '导入并规范化' }));

  expect(await screen.findByText('检测到异常静音，请试听并确认。')).toBeInTheDocument();
  expect(screen.getByText('16 kHz · 单声道 · 1.2 秒')).toBeInTheDocument();
});
