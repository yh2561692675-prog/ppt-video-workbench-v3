import { Img, staticFile } from 'remotion';

import type { ProjectVideoProps, SubtitleCue, SubtitlePlacement, VideoPageProps } from './types';
import { msToFrames } from './types';
import { pageProgress, pageScale, SAFE_ZONE } from './animation';

type TechBoardTemplateProps = {
  page: VideoPageProps;
  subtitles: SubtitleCue[];
  frame: number;
  fps: ProjectVideoProps['fps'];
  width: ProjectVideoProps['width'];
  height: ProjectVideoProps['height'];
  reducedMotion: boolean;
  placement?: SubtitlePlacement;
  includeSubtitles?: boolean;
};

export function TechBoardTemplate({
  page,
  subtitles,
  frame,
  fps,
  width,
  height,
  reducedMotion,
  placement,
  includeSubtitles = true,
}: TechBoardTemplateProps) {
  const startFrame = msToFrames(page.start_ms, fps);
  const endFrame = msToFrames(page.end_ms, fps);
  const progress = pageProgress(frame, startFrame, endFrame);
  const frameMs = (frame * 1_000) / fps;
  const activeSubtitle = subtitles.find(
    (cue) => cue.page_id === page.page_id && cue.start_ms <= frameMs && frameMs < cue.end_ms,
  );
  const panelPlacement = placement ?? {
    position: 'bottom' as const,
    rect: { x: 192, y: 888, width: 1536, height: 96 },
    panel: false,
    reason: null,
  };

  return (
    <div
      className="tech-board"
      style={{
        position: 'absolute',
        inset: 0,
        width,
        height,
        overflow: 'hidden',
        background: 'linear-gradient(135deg, #07111f 0%, #0b2031 55%, #07111f 100%)',
      }}
    >
      <Img
        src={assetSource(page.image_path)}
        className="page-image"
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          transform: pageScale(progress, reducedMotion),
          opacity: 0.92,
        }}
      />
      <div
        className="center-fog"
        style={{
          position: 'absolute',
          inset: '20% 24%',
          borderRadius: '50%',
          background: 'radial-gradient(circle, rgb(71 230 208 / 18%), transparent 70%)',
          filter: 'blur(24px)',
          pointerEvents: 'none',
        }}
      />
      <div
        className="forward-grid"
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 0,
          height: '23%',
          opacity: reducedMotion ? 0.12 : 0.28,
          background:
            'linear-gradient(rgb(71 230 208 / 30%) 1px, transparent 1px), linear-gradient(90deg, rgb(71 230 208 / 24%) 1px, transparent 1px)',
          backgroundSize: '44px 22px',
          transform: reducedMotion
            ? 'none'
            : `perspective(260px) rotateX(58deg) translateY(${progress * 12}px)`,
          transformOrigin: 'bottom center',
        }}
      />
      <div
        className="scanline"
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          top: `${(progress * 100).toFixed(2)}%`,
          height: 2,
          background: 'rgb(71 230 208 / 54%)',
          boxShadow: '0 0 24px rgb(71 230 208 / 70%)',
          opacity: reducedMotion ? 0.2 : 0.65,
        }}
      />
      <div
        className="safe-zone"
        style={{
          position: 'absolute',
          left: `${SAFE_ZONE * 100}%`,
          right: `${SAFE_ZONE * 100}%`,
          top: `${SAFE_ZONE * 100}%`,
          bottom: `${SAFE_ZONE * 100}%`,
          border: '1px solid rgb(71 230 208 / 16%)',
          pointerEvents: 'none',
        }}
      />
      <div
        className="focus-frame"
        style={{
          position: 'absolute',
          left: '7%',
          top: '9%',
          width: '22%',
          height: '24%',
          border: '1px solid rgb(71 230 208 / 65%)',
          boxShadow: '0 0 24px rgb(71 230 208 / 22%)',
          opacity: reducedMotion ? 0.45 : 0.75,
        }}
      />
      <div
        className="keyword-highlight"
        style={{
          position: 'absolute',
          left: '7%',
          top: '7%',
          color: '#47e6d0',
          fontSize: 18,
          letterSpacing: '0.18em',
          textShadow: '0 0 16px rgb(71 230 208 / 80%)',
        }}
      >
        {page.title || `PAGE ${page.page_order}`}
      </div>
      {includeSubtitles && activeSubtitle && (
        <div
          className="subtitle-panel"
          style={{
            position: 'absolute',
            left: `${(panelPlacement.rect.x / width) * 100}%`,
            width: `${(panelPlacement.rect.width / width) * 100}%`,
            top: `${(panelPlacement.rect.y / height) * 100}%`,
            minHeight: `${(panelPlacement.rect.height / height) * 100}%`,
            padding: '14px 24px',
            color: '#f5fbff',
            border: '1px solid rgb(71 230 208 / 52%)',
            borderRadius: 12,
            background: panelPlacement.panel ? 'rgb(4 17 29 / 86%)' : 'rgb(4 17 29 / 76%)',
            boxShadow: '0 0 28px rgb(0 0 0 / 35%)',
            textAlign: 'center',
            fontSize: 30,
            lineHeight: 1.35,
          }}
        >
          {activeSubtitle.text}
        </div>
      )}
    </div>
  );
}

function assetSource(path: string): string {
  return path.startsWith('/') ? path : staticFile(path);
}
