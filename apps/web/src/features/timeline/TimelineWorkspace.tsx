import { useMemo, useState } from 'react';

export interface TimelineClipView {
  id: string;
  kind: string;
  start_us: number;
  duration_us: number;
  source_ref: string;
  locked?: boolean;
  payload?: Record<string, unknown>;
}

export interface TimelineTrackView {
  id: string;
  name: string;
  kind: string;
  order: number;
  muted?: boolean;
  locked?: boolean;
  clips: TimelineClipView[];
}

interface TimelineWorkspaceProps {
  durationUs: number;
  revision: number;
  tracks: TimelineTrackView[];
  onSelectClip: (clipId: string) => void;
  onCommand: (command: { kind: string; payload: Record<string, unknown> }) => void;
  selectedClipIds?: string[];
}

export function TimelineWorkspace({
  durationUs,
  revision,
  tracks,
  onSelectClip,
  onCommand,
  selectedClipIds,
}: TimelineWorkspaceProps) {
  const orderedTracks = useMemo(() => [...tracks].sort((a, b) => a.order - b.order), [tracks]);
  const [localSelection, setLocalSelection] = useState<string[]>([]);
  const selection = selectedClipIds ?? localSelection;
  const safeDuration = Math.max(durationUs, 1);

  function selectClip(clipId: string) {
    if (selectedClipIds === undefined) setLocalSelection([clipId]);
    onSelectClip(clipId);
  }

  const selectedClipId = selection[0];

  return (
    <section className="timeline-workspace" aria-label="统一多轨时间线">
      <div className="timeline-heading">
        <div>
          <h3>统一多轨时间线</h3>
          <p className="muted">
            Revision {revision} · {Math.round(durationUs / 1_000_000)} 秒
          </p>
        </div>
        <div className="timeline-actions">
          <button
            className="secondary"
            onClick={() =>
              onCommand({
                kind: 'split_clip',
                payload: selectedClipId ? { clip_id: selectedClipId } : {},
              })
            }
          >
            分割
          </button>
          <button
            className="secondary"
            onClick={() =>
              onCommand({
                kind: 'delete_clip',
                payload: selectedClipId ? { clip_id: selectedClipId } : {},
              })
            }
          >
            删除
          </button>
          <button className="primary" onClick={() => onCommand({ kind: 'compile', payload: {} })}>
            编译 RenderGraph
          </button>
        </div>
      </div>
      <div className="timeline-ruler" aria-hidden="true">
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
          <span key={ratio} style={{ left: `${ratio * 100}%` }}>
            {Math.round((durationUs * ratio) / 1_000_000)}s
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
            <div className="timeline-lane">
              {track.clips.map((clip) => (
                <button
                  className={`timeline-clip timeline-clip-${clip.kind}`}
                  key={clip.id}
                  style={{
                    left: `${(clip.start_us / safeDuration) * 100}%`,
                    width: `${(clip.duration_us / safeDuration) * 100}%`,
                  }}
                  onClick={() => selectClip(clip.id)}
                  aria-pressed={selection.includes(clip.id)}
                  data-selected={selection.includes(clip.id) ? 'true' : undefined}
                  disabled={clip.locked}
                  title={clip.source_ref}
                >
                  <span>{clip.source_ref}</span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
