export type FrameRange = { start: number; end: number };

export function usToFrameFloor(valueUs: number, fps: number): number {
  if (valueUs < 0 || fps <= 0) throw new Error('时间和 FPS 必须为正数或零');
  return Math.floor((valueUs * fps) / 1_000_000);
}

export function usToFrameCeil(valueUs: number, fps: number): number {
  if (valueUs < 0 || fps <= 0) throw new Error('时间和 FPS 必须为正数或零');
  return Math.ceil((valueUs * fps) / 1_000_000);
}

export function usRangeToFrames(startUs: number, endUs: number, fps: number): FrameRange {
  if (endUs <= startUs) throw new Error('时间范围必须满足 end > start');
  const start = usToFrameFloor(startUs, fps);
  const end = Math.max(start + 1, usToFrameCeil(endUs - 1, fps));
  return { start, end };
}

export function durationToFrames(durationUs: number, fps: number): number {
  if (durationUs < 0 || fps <= 0) throw new Error('时长和 FPS 必须为正数或零');
  return Math.max(1, usToFrameCeil(durationUs, fps));
}

export function usToFrames(valueUs: number, fps: number): number {
  return usToFrameFloor(valueUs, fps);
}
