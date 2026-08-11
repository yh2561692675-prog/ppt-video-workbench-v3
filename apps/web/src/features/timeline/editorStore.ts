import { createStore } from 'zustand/vanilla';

export interface TimelineIntent {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  baseRevision: number;
}

export interface TimelineViewportState {
  scrollLeft: number;
  width: number;
  pixelsPerSecond: number;
}

export interface TimelinePreviewState {
  mode: 'interactive' | 'authoritative';
  jobId: string | null;
  status: string;
  cacheKey: string | null;
}

export interface TimelineEditorState {
  serverRevision: number;
  timelineHash: string;
  graphRevision: number | null;
  graphHash: string | null;
  staleReasons: string[];
  pendingIntents: TimelineIntent[];
  conflict: { intentId: string; serverRevision: number; reason: string } | null;
  viewport: TimelineViewportState;
  preview: TimelinePreviewState;
  queueIntent: (intent: Omit<TimelineIntent, 'baseRevision'>) => void;
  acknowledgeIntent: (intentId: string, revision: number, timelineHash: string) => void;
  recordConflict: (intentId: string, serverRevision: number, reason: string) => void;
  adoptGraph: (revision: number, hash: string, staleReasons: string[]) => void;
  setViewport: (viewport: Partial<TimelineViewportState>) => void;
  setPreview: (preview: Partial<TimelinePreviewState>) => void;
}

export function createTimelineEditorStore(
  initial: Pick<TimelineEditorState, 'serverRevision' | 'timelineHash'>,
) {
  return createStore<TimelineEditorState>((set, get) => ({
    ...initial,
    graphRevision: null,
    graphHash: null,
    staleReasons: [],
    pendingIntents: [],
    conflict: null,
    viewport: { scrollLeft: 0, width: 1000, pixelsPerSecond: 100 },
    preview: { mode: 'interactive', jobId: null, status: 'idle', cacheKey: null },
    queueIntent: (intent) =>
      set({
        pendingIntents: [
          ...get().pendingIntents,
          { ...intent, baseRevision: get().serverRevision },
        ],
      }),
    acknowledgeIntent: (intentId, revision, timelineHash) =>
      set({
        serverRevision: revision,
        timelineHash,
        pendingIntents: get().pendingIntents.filter((intent) => intent.id !== intentId),
        conflict: get().conflict?.intentId === intentId ? null : get().conflict,
      }),
    recordConflict: (intentId, serverRevision, reason) =>
      set({ serverRevision, conflict: { intentId, serverRevision, reason } }),
    adoptGraph: (graphRevision, graphHash, staleReasons) =>
      set({ graphRevision, graphHash, staleReasons: [...staleReasons] }),
    setViewport: (viewport) => set({ viewport: { ...get().viewport, ...viewport } }),
    setPreview: (preview) => set({ preview: { ...get().preview, ...preview } }),
  }));
}

export function replayIntents(intents: TimelineIntent[], serverRevision: number) {
  return intents.map((intent, index) => ({
    command_id: intent.id,
    expected_revision: serverRevision + index,
    kind: intent.kind,
    payload: intent.payload,
  }));
}
