export const SAFE_ZONE = 0.05;
export const SUBTITLE_SAFE_BOTTOM = 0.08;

export function pageProgress(frame: number, startFrame: number, endFrame: number): number {
  const duration = Math.max(1, endFrame - startFrame);
  return Math.min(1, Math.max(0, (frame - startFrame) / duration));
}

export function pageScale(progress: number, reducedMotion: boolean): string {
  return reducedMotion ? 'none' : `scale(${(1 + progress * 0.02).toFixed(4)})`;
}
