import type { SubtitleCue, SubtitlePlacement, VideoPageProps } from './types';

export function SubtitleLayer({
  page,
  subtitles,
  placement,
  frame,
  fps,
  width,
  height,
}: {
  page: VideoPageProps;
  subtitles: SubtitleCue[];
  placement?: SubtitlePlacement;
  frame: number;
  fps: number;
  width: number;
  height: number;
}) {
  const frameMs = (frame * 1_000) / fps;
  const active = subtitles.find(
    (cue) => cue.page_id === page.page_id && cue.start_ms <= frameMs && frameMs < cue.end_ms,
  );
  if (!active) return null;
  const rect = placement?.rect ?? { x: width * 0.1, y: height * 0.82, width: width * 0.8, height: 96 };
  return (
    <div
      className="subtitle-layer"
      style={{
        position: 'absolute',
        left: rect.x,
        top: rect.y,
        width: rect.width,
        minHeight: rect.height,
        zIndex: 10,
        padding: '14px 24px',
        color: '#f5fbff',
        borderRadius: 12,
        background: placement?.panel ? 'rgb(4 17 29 / 86%)' : 'rgb(4 17 29 / 76%)',
        textAlign: 'center',
        fontSize: Math.max(22, width / 64),
        lineHeight: 1.35,
      }}
    >
      {active.text}
    </div>
  );
}
