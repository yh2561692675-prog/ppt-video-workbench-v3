import { render, screen } from '@testing-library/react';
import { expect, it } from 'vitest';

import { AudioGatePanel } from './AudioGatePanel';

it('shows why subtitle navigation is blocked and which page needs action', () => {
  render(
    <AudioGatePanel
      gate={{
        allowed: false,
        reasons: [
          {
            code: 'audio_difference_unconfirmed',
            message: '本页存在未由人工确认的普通录音差异',
            page_id: 'page-3',
            action: '请人工确认该差异处理方式',
          },
        ],
      }}
      pageLabels={{ 'page-3': '第3页' }}
    />,
  );

  expect(screen.getByText('音频门禁未通过')).toBeInTheDocument();
  expect(screen.getByText('第3页：')).toBeInTheDocument();
  expect(screen.getByText('本页存在未由人工确认的普通录音差异')).toBeInTheDocument();
  expect(screen.getByText('请人工确认该差异处理方式')).toBeInTheDocument();
});

it('shows that subtitle work is available after the audio gate passes', () => {
  render(<AudioGatePanel gate={{ allowed: true, reasons: [] }} />);

  expect(screen.getByText('音频门禁已通过，可进入字幕步骤。')).toBeInTheDocument();
});
