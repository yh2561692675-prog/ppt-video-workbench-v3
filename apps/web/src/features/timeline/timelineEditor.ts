export interface SnapPoint {
  timeUs: number;
  kind: 'clip-start' | 'clip-end' | 'page' | 'subtitle' | 'marker' | 'playhead';
  id: string;
}

export interface TimelineSelection {
  clipIds: string[];
  anchorClipId: string | null;
}

export interface DragPreview {
  clipId: string;
  startUs: number;
  durationUs: number;
  trackId: string;
}

export interface VisibleTimeRange {
  startUs: number;
  endUs: number;
}

export function timeToPixels(timeUs: number, pixelsPerSecond: number): number {
  return (Math.max(0, timeUs) / 1_000_000) * Math.max(0, pixelsPerSecond);
}

export function visibleTimeRange(
  scrollLeft: number,
  viewportWidth: number,
  pixelsPerSecond: number,
  overscanPx = 300,
): VisibleTimeRange {
  const startPx = Math.max(0, scrollLeft - overscanPx);
  const endPx = Math.max(startPx, scrollLeft + viewportWidth + overscanPx);
  return {
    startUs: Math.floor((startPx / pixelsPerSecond) * 1_000_000),
    endUs: Math.ceil((endPx / pixelsPerSecond) * 1_000_000),
  };
}

export function zoomAroundAnchor(
  currentPixelsPerSecond: number,
  nextPixelsPerSecond: number,
  scrollLeft: number,
  anchorViewportX: number,
): number {
  const anchorTimeSeconds = (scrollLeft + anchorViewportX) / currentPixelsPerSecond;
  return Math.max(0, anchorTimeSeconds * nextPixelsPerSecond - anchorViewportX);
}

export function waveformLevelForViewport(microsecondsPerPixel: number): number {
  if (microsecondsPerPixel <= 10_000) return 0;
  if (microsecondsPerPixel <= 50_000) return 1;
  if (microsecondsPerPixel <= 250_000) return 2;
  return 3;
}

export function requestMatchesRevision(requestRevision: number, serverRevision: number): boolean {
  return requestRevision === serverRevision;
}

export function visibleClips<T extends { start_us: number; duration_us: number }>(
  clips: T[],
  range: VisibleTimeRange,
): T[] {
  return clips.filter(
    (clip) => clip.start_us < range.endUs && clip.start_us + clip.duration_us > range.startUs,
  );
}

/** Convert a pointer delta into an integer microsecond position. */
export function timeFromPointer(
  pointerX: number,
  laneLeft: number,
  pixelsPerSecond: number,
): number {
  if (!Number.isFinite(pointerX) || !Number.isFinite(laneLeft) || pixelsPerSecond <= 0) {
    return 0;
  }
  return Math.max(0, Math.round(((pointerX - laneLeft) / pixelsPerSecond) * 1_000_000));
}

/** Snap only when the nearest point is inside the current zoom-dependent threshold. */
export function snapTimeUs(
  timeUs: number,
  points: SnapPoint[],
  pixelsPerSecond: number,
  thresholdPx = 8,
): number {
  if (!Number.isFinite(timeUs) || pixelsPerSecond <= 0 || points.length === 0) return timeUs;
  const thresholdUs = Math.max(1, Math.round((thresholdPx / pixelsPerSecond) * 1_000_000));
  let nearest: SnapPoint | undefined;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const point of points) {
    const distance = Math.abs(point.timeUs - timeUs);
    if (
      distance < nearestDistance ||
      (distance === nearestDistance && point.id < (nearest?.id ?? ''))
    ) {
      nearest = point;
      nearestDistance = distance;
    }
  }
  return nearest && nearestDistance <= thresholdUs ? nearest.timeUs : timeUs;
}

export function updateSelection(
  current: TimelineSelection,
  clipId: string,
  options: { additive?: boolean; range?: string[] } = {},
): TimelineSelection {
  if (options.range) {
    return { clipIds: [...options.range], anchorClipId: clipId };
  }
  if (options.additive) {
    const clipIds = current.clipIds.includes(clipId)
      ? current.clipIds.filter((id) => id !== clipId)
      : [...current.clipIds, clipId];
    return { clipIds, anchorClipId: clipId };
  }
  return { clipIds: [clipId], anchorClipId: clipId };
}

export function createMovePreview(
  clip: { id: string; trackId: string; startUs: number; durationUs: number },
  pointerX: number,
  laneLeft: number,
  pixelsPerSecond: number,
  snapPoints: SnapPoint[],
  snapEnabled = true,
): DragPreview {
  const rawStart = timeFromPointer(pointerX, laneLeft, pixelsPerSecond);
  const startUs = snapEnabled ? snapTimeUs(rawStart, snapPoints, pixelsPerSecond) : rawStart;
  return {
    clipId: clip.id,
    trackId: clip.trackId,
    startUs: Math.max(0, startUs),
    durationUs: clip.durationUs,
  };
}
