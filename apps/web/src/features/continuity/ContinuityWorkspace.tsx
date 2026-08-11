import type { ContinuityPlanRecord } from '../../api/client';

interface ContinuityWorkspaceProps {
  plan: ContinuityPlanRecord;
  pageLabels?: Record<string, string>;
  onCommand: (command: { kind: string; payload: Record<string, unknown> }) => void;
}

export function ContinuityWorkspace({
  plan,
  pageLabels = {},
  onCommand,
}: ContinuityWorkspaceProps) {
  return (
    <section className="continuity-workspace" aria-label="转场与连续镜头">
      <div className="continuity-heading">
        <div>
          <h3>转场与连续镜头</h3>
          <p className="muted">
            Revision {plan.revision} · {plan.transitions.length} 个转场 · {plan.overlays.length}{' '}
            个覆盖层
          </p>
        </div>
        <button
          type="button"
          className="secondary"
          onClick={() =>
            onCommand({
              kind: 'upsert_overlay',
              payload: {
                source_ref: 'assets/brand/logo.png',
                kind: 'logo',
                start_ms: 0,
                duration_ms: Math.max(plan.duration_ms, 1000),
                x: 0.82,
                y: 0.06,
                width: 0.12,
                height: 0.08,
              },
            })
          }
        >
          添加 Logo 覆盖层
        </button>
      </div>
      <div className="continuity-grid">
        <div className="continuity-transitions">
          <h4>跨页转场 / J-L Cut</h4>
          {plan.transitions.map((transition) => (
            <div className="continuity-transition-row" key={transition.id}>
              <span>
                {pageLabels[transition.from_page_id] ?? transition.from_page_id.slice(0, 8)} →{' '}
                {pageLabels[transition.to_page_id] ?? transition.to_page_id.slice(0, 8)}
              </span>
              <select
                aria-label="转场类型"
                value={transition.kind}
                onChange={(event) =>
                  onCommand({
                    kind: 'upsert_transition',
                    payload: {
                      transition: { ...transition, kind: event.target.value },
                    },
                  })
                }
              >
                <option value="cut">直接切换</option>
                <option value="dissolve">叠化</option>
                <option value="wipe">擦除</option>
                <option value="slide">滑动</option>
                <option value="match">连续镜头</option>
              </select>
              <select
                aria-label="音频切点"
                value={transition.audio_mode}
                onChange={(event) =>
                  onCommand({
                    kind: 'upsert_transition',
                    payload: {
                      transition: {
                        ...transition,
                        audio_mode: event.target.value,
                        audio_offset_ms:
                          event.target.value === 'cut' ? 0 : transition.audio_offset_ms,
                      },
                    },
                  })
                }
              >
                <option value="cut">音画同切</option>
                <option value="j_cut">J Cut（声音先入）</option>
                <option value="l_cut">L Cut（声音后出）</option>
              </select>
              <input
                aria-label="转场时长"
                type="number"
                min={0}
                max={10000}
                value={transition.duration_ms}
                onChange={(event) =>
                  onCommand({
                    kind: 'upsert_transition',
                    payload: {
                      transition: { ...transition, duration_ms: Number(event.target.value) },
                    },
                  })
                }
              />
              <span className="muted">ms</span>
            </div>
          ))}
          {plan.transitions.length === 0 && <p className="muted">暂无跨页转场。</p>}
        </div>
        <div className="continuity-overlays">
          <h4>媒体覆盖层</h4>
          {plan.overlays.map((overlay) => (
            <div className="continuity-overlay-row" key={overlay.id}>
              <strong>{overlay.kind}</strong>
              <span>{overlay.source_ref}</span>
              <span>
                {Math.round(overlay.x * 100)}%, {Math.round(overlay.y * 100)}% ·{' '}
                {overlay.duration_ms} ms
              </span>
              <button
                type="button"
                className="secondary"
                onClick={() =>
                  onCommand({ kind: 'remove_overlay', payload: { overlay_id: overlay.id } })
                }
              >
                移除
              </button>
            </div>
          ))}
          {plan.overlays.length === 0 && <p className="muted">暂无覆盖层。</p>}
        </div>
      </div>
      <div className="continuity-chapters">
        <h4>章节过渡</h4>
        {plan.chapters.length === 0 ? (
          <p className="muted">尚未建立章节标记。</p>
        ) : (
          plan.chapters.map((chapter) => (
            <span className="continuity-chapter-chip" key={chapter.id}>
              {chapter.title} · {chapter.start_ms}–{chapter.end_ms} ms
            </span>
          ))
        )}
      </div>
    </section>
  );
}
