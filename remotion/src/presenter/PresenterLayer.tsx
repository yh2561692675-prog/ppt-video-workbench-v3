import { Video } from 'remotion';
import { interpolate, staticFile, useCurrentFrame } from 'remotion';

import type { PresenterTimeline } from '../video/types';
import { msToFrames } from '../video/types';
import { getPresenterRenderState } from './presenterRenderState';
import { presenterBoxStyle } from './presenterStyle';

export function PresenterLayer({
  source,
  timeline,
  fps,
  width,
  height,
  reducedMotion,
}: {
  source: string;
  timeline: PresenterTimeline;
  fps: number;
  width: number;
  height: number;
  reducedMotion: boolean;
}) {
  const frame = useCurrentFrame();
  const state = getPresenterRenderState(frame, fps, timeline);
  if (!state.videoVisible || !state.segment) return null;
  const startFrame = msToFrames(state.segment.start_ms, fps);
  const endFrame = msToFrames(state.segment.end_ms, fps);
  const transitionFrames = Math.max(1, Math.min(6, Math.floor((endFrame - startFrame) / 2)));
  const enterEnd = startFrame + transitionFrames;
  const exitStart = endFrame - transitionFrames;
  return (
    <div
      data-presenter-layout={state.segment.layout}
      style={{
        ...presenterBoxStyle(state.segment, width, height),
        opacity: reducedMotion
          ? 1
          : Math.min(
              interpolate(frame, [startFrame, enterEnd], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
              }),
              interpolate(frame, [exitStart, endFrame], [1, 0], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
              }),
            ),
        scale: reducedMotion
          ? 1
          : interpolate(frame, [startFrame, enterEnd], [0.97, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            }),
      }}
    >
      <Video
        muted
        src={assetSource(source)}
        style={{ width: '100%', height: '100%', objectFit: 'cover' }}
      />
    </div>
  );
}

function assetSource(path: string): string {
  return path.startsWith('/') ? path : staticFile(path);
}
