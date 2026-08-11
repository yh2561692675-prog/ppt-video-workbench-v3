import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ExportPresetRecord } from '../../api/client';
import { ExportPresetWorkspace } from './ExportPresetWorkspace';

const presets: ExportPresetRecord[] = [
  {
    id: 'master-1080p-30',
    label: '主母版 1080p 30fps',
    platform: 'master',
    width: 1920,
    height: 1080,
    fps: 30,
    video_bitrate: '12M',
    audio_bitrate: '192k',
    container: 'mp4',
    video_codec: 'libx264',
    max_segment_seconds: null,
  },
  {
    id: 'douyin-square-1080p-30',
    label: '抖音方屏 1080p',
    platform: 'douyin',
    width: 1080,
    height: 1080,
    fps: 30,
    video_bitrate: '10M',
    audio_bitrate: '160k',
    container: 'mp4',
    video_codec: 'libx264',
    max_segment_seconds: 60,
  },
];

describe('ExportPresetWorkspace', () => {
  it('selects a platform preset and creates a plan', () => {
    const onCreatePlan = vi.fn();
    render(<ExportPresetWorkspace presets={presets} plans={[]} onCreatePlan={onCreatePlan} />);
    fireEvent.change(screen.getByLabelText('导出预设'), {
      target: { value: 'douyin-square-1080p-30' },
    });
    fireEvent.click(screen.getByRole('button', { name: '生成导出计划' }));
    expect(onCreatePlan).toHaveBeenCalledWith('douyin-square-1080p-30');
  });
});
