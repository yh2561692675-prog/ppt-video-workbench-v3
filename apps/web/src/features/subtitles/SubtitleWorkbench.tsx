import { useMemo, useState } from 'react';

import type { SubtitleWorkbenchCueRecord, SubtitleWorkbenchRecord } from '../../api/client';

interface SubtitleWorkbenchProps {
  document: SubtitleWorkbenchRecord;
  onCommand: (command: { kind: string; payload: Record<string, unknown> }) => void;
  onTranslate?: (language: string) => void;
}

export function SubtitleWorkbench({ document, onCommand, onTranslate }: SubtitleWorkbenchProps) {
  const primary = document.tracks.find((track) => track.primary) ?? document.tracks[0];
  const [selectedCueId, setSelectedCueId] = useState(primary?.cues[0]?.id ?? null);
  const selectedCue = useMemo(
    () => primary?.cues.find((cue) => cue.id === selectedCueId) ?? primary?.cues[0],
    [primary, selectedCueId],
  );

  if (!primary) return null;

  return (
    <section className="subtitle-workbench" aria-label="高级字幕工作台">
      <div className="subtitle-workbench-heading">
        <div>
          <h3>高级字幕工作台</h3>
          <p className="muted">
            Revision {document.revision} · {document.tracks.length} 条语言轨 · {primary.cues.length}{' '}
            条字幕
          </p>
        </div>
        <label className="subtitle-render-mode">
          输出模式
          <select
            value={document.render_mode}
            onChange={(event) =>
              onCommand({ kind: 'set_render_mode', payload: { render_mode: event.target.value } })
            }
          >
            <option value="soft">软字幕</option>
            <option value="burn_in">烧录字幕</option>
          </select>
        </label>
      </div>
      <div className="subtitle-workbench-layout">
        <div className="subtitle-cue-list" role="list" aria-label="字幕条目">
          {primary.cues.map((cue) => (
            <button
              type="button"
              role="listitem"
              key={cue.id}
              className={cue.id === selectedCue?.id ? 'selected' : ''}
              onClick={() => setSelectedCueId(cue.id)}
            >
              <span>{formatTime(cue.start_ms)}</span>
              <strong>{cue.text}</strong>
              <small>{formatTime(cue.end_ms)}</small>
            </button>
          ))}
        </div>
        <div className="subtitle-cue-editor">
          {selectedCue ? (
            <CueEditor
              cue={selectedCue}
              language={primary.language}
              style={selectedCue.style_override ?? document.default_style}
              onCommand={onCommand}
            />
          ) : (
            <p className="muted">暂无字幕条目，请先生成字幕时间轴。</p>
          )}
          <div className="subtitle-language-actions">
            {document.tracks.map((track) => (
              <span className="subtitle-language-chip" key={track.id}>
                {track.label} · {track.visible ? '显示' : '隐藏'}
              </span>
            ))}
            {onTranslate && (
              <button type="button" className="secondary" onClick={() => onTranslate('en')}>
                添加英文轨
              </button>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

function CueEditor({
  cue,
  language,
  style,
  onCommand,
}: {
  cue: SubtitleWorkbenchCueRecord;
  language: string;
  style: SubtitleWorkbenchRecord['default_style'];
  onCommand: SubtitleWorkbenchProps['onCommand'];
}) {
  return (
    <div className="subtitle-cue-form">
      <label>
        文本
        <textarea
          value={cue.text}
          onChange={(event) =>
            onCommand({
              kind: 'update_cue',
              payload: { language, cue_id: cue.id, text: event.target.value },
            })
          }
          rows={3}
        />
      </label>
      <div className="subtitle-time-fields">
        <label>
          开始 (ms)
          <input
            type="number"
            value={cue.start_ms}
            onChange={(event) =>
              onCommand({
                kind: 'retime_cue',
                payload: {
                  language,
                  cue_id: cue.id,
                  start_ms: Number(event.target.value),
                  end_ms: cue.end_ms,
                },
              })
            }
          />
        </label>
        <label>
          结束 (ms)
          <input
            type="number"
            value={cue.end_ms}
            onChange={(event) =>
              onCommand({
                kind: 'retime_cue',
                payload: {
                  language,
                  cue_id: cue.id,
                  start_ms: cue.start_ms,
                  end_ms: Number(event.target.value),
                },
              })
            }
          />
        </label>
      </div>
      <div className="subtitle-style-controls">
        <label>
          字体
          <input
            value={style.font_family}
            onChange={(event) =>
              onCommand({
                kind: 'set_style',
                payload: {
                  language,
                  cue_id: cue.id,
                  style: { ...style, font_family: event.target.value },
                },
              })
            }
          />
        </label>
        <label>
          字号
          <input
            type="number"
            min={8}
            max={240}
            value={style.font_size}
            onChange={(event) =>
              onCommand({
                kind: 'set_style',
                payload: {
                  language,
                  cue_id: cue.id,
                  style: { ...style, font_size: Number(event.target.value) },
                },
              })
            }
          />
        </label>
        <label>
          颜色
          <input
            type="color"
            value={style.color}
            onChange={(event) =>
              onCommand({
                kind: 'set_style',
                payload: {
                  language,
                  cue_id: cue.id,
                  style: { ...style, color: event.target.value },
                },
              })
            }
          />
        </label>
        <label className="subtitle-checkbox">
          <input
            type="checkbox"
            checked={style.animation === 'word_highlight'}
            onChange={(event) =>
              onCommand({
                kind: 'set_style',
                payload: {
                  language,
                  cue_id: cue.id,
                  style: { ...style, animation: event.target.checked ? 'word_highlight' : 'none' },
                },
              })
            }
          />
          逐词高亮
        </label>
      </div>
    </div>
  );
}

function formatTime(milliseconds: number): string {
  const seconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(seconds / 60);
  return `${String(minutes).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}.${String(
    milliseconds % 1000,
  ).padStart(3, '0')}`;
}
