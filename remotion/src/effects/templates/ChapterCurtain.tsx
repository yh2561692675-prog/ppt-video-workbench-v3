import type { CSSProperties } from 'react';

/* eslint-disable react-refresh/only-export-components */

export type ChapterPalette = 'blue' | 'gold' | 'red' | 'teal';

export function validateChapterDuration(durationMs: number): { ok: boolean; reason?: string } {
  if (durationMs < 1200 || durationMs > 2500) {
    return { ok: false, reason: '章节幕时长必须在 1.2—2.5 秒之间' };
  }
  return { ok: true };
}

export function ChapterCurtain({
  chapterNumber,
  chapterTitle,
  palette,
  durationMs,
}: {
  chapterNumber?: string;
  chapterTitle: string;
  palette: ChapterPalette;
  durationMs: number;
}) {
  const validation = validateChapterDuration(durationMs);
  if (!validation.ok) throw new Error(validation.reason);
  const colors: Record<ChapterPalette, string> = {
    blue: '#47a7ff',
    gold: '#f5c15d',
    red: '#ff756d',
    teal: '#47e6d0',
  };
  const style: CSSProperties = {
    position: 'absolute',
    inset: 0,
    display: 'grid',
    placeContent: 'center',
    gap: 16,
    color: '#f5fbff',
    background: `radial-gradient(circle at 50% 45%, ${colors[palette]}33, transparent 58%), #07111f`,
    textAlign: 'center',
  };
  return (
    <div className="chapter-curtain" data-palette={palette} style={style}>
      {chapterNumber && (
        <div className="chapter-number" style={{ color: colors[palette], fontSize: 64 }}>
          {chapterNumber}
        </div>
      )}
      <div className="chapter-title" style={{ fontSize: 48, letterSpacing: '0.08em' }}>
        {chapterTitle}
      </div>
    </div>
  );
}
