import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { SubtitleWorkbenchRecord } from '../../api/client';
import { SubtitleWorkbench } from './SubtitleWorkbench';

const style = {
  id: 'style-1',
  name: '默认模板',
  font_family: 'Noto Sans CJK SC',
  font_size: 48,
  color: '#FFFFFF',
  outline_color: '#000000',
  outline_width: 2,
  background_color: '#000000',
  background_opacity: 0.5,
  position: 'bottom' as const,
  animation: 'none' as const,
  highlight_color: '#FFD54F',
};

const document: SubtitleWorkbenchRecord = {
  version: 2,
  revision: 3,
  duration_ms: 5000,
  render_mode: 'soft',
  default_style: style,
  templates: [style],
  updated_at: '2026-08-11T00:00:00Z',
  content_hash: 'a'.repeat(64),
  tracks: [
    {
      id: 'track-1',
      language: 'zh-CN',
      label: '中文',
      primary: true,
      visible: true,
      cues: [
        {
          id: 'cue-1',
          start_ms: 0,
          end_ms: 2500,
          text: '你好世界',
          translation: null,
          words: [],
          style_template_id: null,
          style_override: null,
          line_breaks: [],
          source_word_indexes: [],
          locked: false,
        },
      ],
    },
  ],
};

describe('SubtitleWorkbench', () => {
  it('edits style, switches render mode and requests translation', () => {
    const onCommand = vi.fn();
    const onTranslate = vi.fn();
    render(
      <SubtitleWorkbench document={document} onCommand={onCommand} onTranslate={onTranslate} />,
    );
    expect(screen.getAllByText('你好世界')).not.toHaveLength(0);
    fireEvent.change(screen.getByLabelText('输出模式'), { target: { value: 'burn_in' } });
    expect(onCommand).toHaveBeenCalledWith({
      kind: 'set_render_mode',
      payload: { render_mode: 'burn_in' },
    });
    fireEvent.click(screen.getByRole('button', { name: '添加英文轨' }));
    expect(onTranslate).toHaveBeenCalledWith('en');
  });
});
