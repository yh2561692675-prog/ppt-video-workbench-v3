import type { ComponentProps } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { TechBoardTemplate } from './TechBoardTemplate';

vi.mock('remotion', () => ({
  Img: (props: ComponentProps<'img'>) => <img {...props} />,
  staticFile: (path: string) => `/${path}`,
}));

const page = {
  page_id: 'page-1',
  page_order: 1,
  title: '智能制造',
  image_path: '02_页面预览/page-0001.png',
  audio_path: '05_音频/page-0001.wav',
  start_ms: 0,
  end_ms: 2000,
  subtitle_cue_ids: ['cue-1'],
};

const subtitle = {
  id: 'cue-1',
  page_id: 'page-1',
  page_order: 1,
  start_ms: 200,
  end_ms: 1200,
  text: '智能制造正在重塑产业。',
  source_word_indexes: [0, 1],
};

describe('TechBoardTemplate', () => {
  it('shows only the subtitle active at the current frame', () => {
    const laterSubtitle = {
      ...subtitle,
      id: 'cue-2',
      start_ms: 1300,
      end_ms: 1800,
      text: '第二条字幕只应在后半页显示。',
    };

    const beforeFirstCue = renderToStaticMarkup(
      <TechBoardTemplate
        page={page}
        subtitles={[subtitle, laterSubtitle]}
        frame={0}
        fps={30}
        width={1920}
        height={1080}
        reducedMotion={false}
      />,
    );
    const duringFirstCue = renderToStaticMarkup(
      <TechBoardTemplate
        page={page}
        subtitles={[subtitle, laterSubtitle]}
        frame={15}
        fps={30}
        width={1920}
        height={1080}
        reducedMotion={false}
      />,
    );
    const duringLaterCue = renderToStaticMarkup(
      <TechBoardTemplate
        page={page}
        subtitles={[subtitle, laterSubtitle]}
        frame={45}
        fps={30}
        width={1920}
        height={1080}
        reducedMotion={false}
      />,
    );

    expect(beforeFirstCue).not.toContain('subtitle-panel');
    expect(duringFirstCue).toContain('智能制造正在重塑产业。');
    expect(duringFirstCue).not.toContain('第二条字幕只应在后半页显示。');
    expect(duringLaterCue).not.toContain('智能制造正在重塑产业。');
    expect(duringLaterCue).toContain('第二条字幕只应在后半页显示。');
  });

  it('renders a whole-page 16:9 board with safe zones and technology layers', () => {
    const html = renderToStaticMarkup(
      <TechBoardTemplate
        page={page}
        subtitles={[subtitle]}
        frame={20}
        fps={30}
        width={1920}
        height={1080}
        reducedMotion={false}
      />,
    );

    expect(html).toContain('tech-board');
    expect(html).toContain('safe-zone');
    expect(html).toContain('scanline');
    expect(html).toContain('forward-grid');
    expect(html).toContain('center-fog');
    expect(html).toContain('focus-frame');
    expect(html).toContain('subtitle-panel');
    expect(html).toContain('keyword-highlight');
    expect(html).toContain('object-fit:contain');
    expect(html).toContain('left:5%');
    expect(html).toContain('right:5%');
  });

  it('disables transform motion when reduced motion is requested', () => {
    const html = renderToStaticMarkup(
      <TechBoardTemplate
        page={page}
        subtitles={[subtitle]}
        frame={20}
        fps={30}
        width={1920}
        height={1080}
        reducedMotion
      />,
    );

    expect(html).toContain('transform:none');
    expect(html).not.toContain('scale(1.');
  });
});
