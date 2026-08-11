import { useMemo, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';

import type { TimelineClipView, TimelineTrackView } from './TimelineWorkspace';
import { timeToPixels, visibleClips, visibleTimeRange, zoomAroundAnchor } from './timelineEditor';

interface Props {
  durationUs: number;
  revision: number;
  fps?: number;
  tracks: TimelineTrackView[];
  onSelectClip: (clipId: string) => void;
  onCommand: (command: { kind: string; payload: Record<string, unknown> }) => void;
  onRestoreRevision?: (revision: number) => void;
  historyRevisions?: number[];
  conflictMessage?: string | null;
  selectedClipIds?: string[];
  onRetryConflict?: () => void;
}

type RichClip = TimelineClipView & { payload?: Record<string, unknown> };

export function EnhancedTimelineWorkspace({
  durationUs,
  revision,
  fps = 30,
  tracks,
  onSelectClip,
  onCommand,
  onRestoreRevision,
  historyRevisions = [],
  conflictMessage,
  selectedClipIds,
  onRetryConflict,
}: Props) {
  const orderedTracks = useMemo(() => [...tracks].sort((a, b) => a.order - b.order), [tracks]);
  const [localSelection, setLocalSelection] = useState<string[]>([]);
  const [pixelsPerSecond, setPixelsPerSecond] = useState(100);
  const [scrollLeft, setScrollLeft] = useState(0);
  const [viewportWidth, setViewportWidth] = useState(1000);
  const [drag, setDrag] = useState<{ clip: RichClip; trackId: string; startX: number } | null>(
    null,
  );
  const scroller = useRef<HTMLDivElement>(null);
  const selection = selectedClipIds ?? localSelection;
  const contentWidth = Math.max(viewportWidth, timeToPixels(durationUs, pixelsPerSecond));
  const visible = visibleTimeRange(scrollLeft, viewportWidth, pixelsPerSecond);
  const selected = orderedTracks
    .flatMap((track) => track.clips)
    .find((clip) => clip.id === selection[0]);
  const frameUs = Math.round(1_000_000 / fps);

  function selectClip(clipId: string) {
    if (selectedClipIds === undefined) setLocalSelection([clipId]);
    onSelectClip(clipId);
  }

  function keyboard(event: KeyboardEvent<HTMLElement>) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
      const prior = [...historyRevisions]
        .filter((value) => value < revision)
        .sort((a, b) => b - a)[0];
      if (prior !== undefined) onRestoreRevision?.(prior);
      event.preventDefault();
      return;
    }
    if (!selected || selected.locked) return;
    if (event.key === 'Delete' || event.key === 'Backspace') {
      onCommand({ kind: 'delete_clip', payload: { clip_id: selected.id } });
      event.preventDefault();
    } else if (event.key.toLowerCase() === 's') {
      onCommand({
        kind: 'split_clip',
        payload: {
          clip_id: selected.id,
          split_at_us: selected.start_us + Math.round(selected.duration_us / 2),
        },
      });
      event.preventDefault();
    } else if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      const delta = (event.key === 'ArrowLeft' ? -1 : 1) * (event.shiftKey ? 1_000_000 : frameUs);
      onCommand(
        event.altKey
          ? {
              kind: 'trim_clip',
              payload: {
                clip_id: selected.id,
                start_us: selected.start_us,
                duration_us: Math.max(frameUs, selected.duration_us + delta),
              },
            }
          : {
              kind: 'move_clip',
              payload: { clip_id: selected.id, start_us: Math.max(0, selected.start_us + delta) },
            },
      );
      event.preventDefault();
    }
  }

  function finishDrag(event: PointerEvent<HTMLDivElement>) {
    if (!drag) return;
    const deltaUs = Math.round(((event.clientX - drag.startX) / pixelsPerSecond) * 1_000_000);
    if (deltaUs !== 0)
      onCommand({
        kind: 'move_clip',
        payload: {
          clip_id: drag.clip.id,
          track_id: drag.trackId,
          start_us: Math.max(0, drag.clip.start_us + deltaUs),
        },
      });
    setDrag(null);
  }

  return (
    <section
      className="timeline-workspace"
      aria-label="统一多轨时间线"
      tabIndex={0}
      onKeyDown={keyboard}
    >
      <div className="timeline-heading">
        <div>
          <h3>统一多轨时间线</h3>
          <p className="muted">
            Revision {revision} · {Math.round(durationUs / 1_000_000)} 秒
          </p>
        </div>
        <div className="timeline-actions">
          <label>
            缩放{' '}
            <input
              aria-label="时间线缩放"
              type="range"
              min={25}
              max={800}
              value={pixelsPerSecond}
              onChange={(event) => {
                const next = Number(event.target.value);
                const element = scroller.current;
                if (element)
                  element.scrollLeft = zoomAroundAnchor(
                    pixelsPerSecond,
                    next,
                    element.scrollLeft,
                    element.clientWidth / 2,
                  );
                setPixelsPerSecond(next);
              }}
            />
          </label>
          <button
            className="secondary"
            disabled={!selected}
            onClick={() =>
              selected &&
              onCommand({
                kind: 'split_clip',
                payload: {
                  clip_id: selected.id,
                  split_at_us: selected.start_us + Math.round(selected.duration_us / 2),
                },
              })
            }
          >
            分割
          </button>
          <button
            className="secondary"
            disabled={!selected}
            onClick={() =>
              selected && onCommand({ kind: 'delete_clip', payload: { clip_id: selected.id } })
            }
          >
            删除
          </button>
          <button className="primary" onClick={() => onCommand({ kind: 'compile', payload: {} })}>
            编译 RenderGraph
          </button>
        </div>
      </div>
      {conflictMessage && (
        <p className="warning" role="alert">
          {conflictMessage}{' '}
          {onRetryConflict && (
            <button className="secondary" onClick={onRetryConflict}>
              按最新版本重试
            </button>
          )}
        </p>
      )}
      {historyRevisions.length > 0 && (
        <details className="timeline-history">
          <summary>历史版本</summary>
          {[...historyRevisions]
            .sort((a, b) => b - a)
            .map((item) => (
              <button
                key={item}
                className="secondary"
                disabled={item === revision}
                onClick={() => onRestoreRevision?.(item)}
              >
                恢复 revision {item}
              </button>
            ))}
        </details>
      )}
      <div
        className="timeline-scroll"
        ref={scroller}
        onScroll={(event) => {
          setScrollLeft(event.currentTarget.scrollLeft);
          setViewportWidth(event.currentTarget.clientWidth);
        }}
        style={{ overflowX: 'auto' }}
      >
        <div style={{ width: contentWidth, minWidth: '100%' }}>
          <div className="timeline-ruler" aria-hidden="true">
            {Array.from({ length: Math.ceil(durationUs / 1_000_000) + 1 }, (_, second) => (
              <span
                key={second}
                style={{ left: timeToPixels(second * 1_000_000, pixelsPerSecond) }}
              >
                {second}s
              </span>
            ))}
          </div>
          <div className="timeline-tracks">
            {orderedTracks.map((track) => (
              <div className="timeline-track" key={track.id}>
                <div className="timeline-track-label">
                  <strong>{track.name}</strong>
                  <small>
                    {track.kind}
                    {track.muted ? ' · 静音' : ''}
                  </small>
                </div>
                <div
                  className="timeline-lane"
                  onPointerUp={finishDrag}
                  onPointerCancel={() => setDrag(null)}
                >
                  {visibleClips(track.clips, visible).map((plainClip) => {
                    const clip = plainClip as RichClip;
                    const status =
                      typeof clip.payload?.derivative_status === 'string'
                        ? clip.payload.derivative_status
                        : null;
                    return (
                      <button
                        className={`timeline-clip timeline-clip-${clip.kind}`}
                        key={clip.id}
                        style={{
                          left: timeToPixels(clip.start_us, pixelsPerSecond),
                          width: Math.max(2, timeToPixels(clip.duration_us, pixelsPerSecond)),
                        }}
                        onClick={() => selectClip(clip.id)}
                        onPointerDown={(event) => {
                          if (!clip.locked) {
                            event.currentTarget.setPointerCapture(event.pointerId);
                            setDrag({ clip, trackId: track.id, startX: event.clientX });
                          }
                        }}
                        aria-pressed={selection.includes(clip.id)}
                        data-selected={selection.includes(clip.id) ? 'true' : undefined}
                        disabled={clip.locked}
                        title={clip.source_ref}
                      >
                        <span>{clip.source_ref}</span>
                        {status && <small>{status}</small>}
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <p className="muted">
        快捷键：S 分割，Delete
        删除，方向键逐帧移动，Shift+方向键逐秒移动，Alt+方向键裁剪，Ctrl/Cmd+Z 撤销。
      </p>
    </section>
  );
}
