import { describe, expect, it } from 'vitest';

import { createTimelineEditorStore, replayIntents } from './editorStore';

describe('timeline editor server state', () => {
  it('keeps a conflicting intent and replays it on the latest revision', () => {
    const store = createTimelineEditorStore({ serverRevision: 4, timelineHash: 'a'.repeat(64) });
    store.getState().queueIntent({ id: 'intent-1', kind: 'move_clip', payload: { clip_id: 'c' } });
    store.getState().recordConflict('intent-1', 7, 'revision conflict');

    expect(store.getState().pendingIntents).toHaveLength(1);
    expect(replayIntents(store.getState().pendingIntents, 7)[0].expected_revision).toBe(7);
    expect(store.getState().conflict?.reason).toBe('revision conflict');
  });

  it('separates graph, viewport and preview state from server timeline revision', () => {
    const store = createTimelineEditorStore({ serverRevision: 2, timelineHash: 'a'.repeat(64) });
    store.getState().adoptGraph(2, 'b'.repeat(64), ['subtitle:soft']);
    store.getState().setViewport({ scrollLeft: 240, pixelsPerSecond: 160 });
    store.getState().setPreview({ mode: 'authoritative', status: 'running' });

    expect(store.getState().serverRevision).toBe(2);
    expect(store.getState().graphHash).toBe('b'.repeat(64));
    expect(store.getState().viewport.scrollLeft).toBe(240);
    expect(store.getState().preview.mode).toBe('authoritative');
  });
});
