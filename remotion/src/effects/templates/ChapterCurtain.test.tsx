import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ChapterCurtain, validateChapterDuration } from './ChapterCurtain';
import { NarrativePreview } from './NarrativePreview';

describe('ChapterCurtain', () => {
  it.each([1000, 3000])('rejects chapter duration %i', (durationMs) => {
    expect(validateChapterDuration(durationMs).ok).toBe(false);
  });

  it('renders the chapter number before the chapter title', () => {
    const html = renderToStaticMarkup(
      <ChapterCurtain
        chapterNumber="01"
        chapterTitle="专业结构"
        palette="gold"
        durationMs={1800}
      />,
    );

    expect(html.indexOf('chapter-number')).toBeLessThan(html.indexOf('chapter-title'));
    expect(html).toContain('chapter-curtain');
  });
});

describe('NarrativePreview', () => {
  it('caps the opening preview at six cards', () => {
    const html = renderToStaticMarkup(
      <NarrativePreview cards={Array.from({ length: 8 }, (_, index) => `栏目 ${index + 1}`)} />,
    );

    expect((html.match(/narrative-preview__card/g) ?? []).length).toBe(6);
    expect(html).toContain('栏目 1');
    expect(html).toContain('栏目 6');
    expect(html).not.toContain('栏目 7');
  });
});
