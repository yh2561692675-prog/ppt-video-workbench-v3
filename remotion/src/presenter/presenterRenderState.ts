import type { PresenterTimeline } from '../video/types';

export type PresenterRenderState = {
  videoVisible: boolean;
  masterAudioEnabled: boolean;
  segment: PresenterTimeline['segments'][number] | null;
};

export function getPresenterRenderState(
  frame: number,
  fps: number,
  timeline: PresenterTimeline,
): PresenterRenderState {
  const timeMs = (frame * 1000) / fps;
  const segment =
    timeline.segments.find((item) => timeMs >= item.start_ms && timeMs < item.end_ms) ?? null;
  return {
    videoVisible: Boolean(segment && segment.layout !== 'hidden'),
    masterAudioEnabled: true,
    segment,
  };
}
