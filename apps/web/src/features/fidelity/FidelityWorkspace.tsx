export type FidelityLevel = 'F0' | 'F1' | 'F2' | 'F3';

export interface MotionCueView {
  cue_id: string;
  shape_ids: string[];
  entrance?: string | null;
  duration_ms: number;
  support: 'supported' | 'degraded' | 'native_capture_required' | 'unsupported';
}

export interface FidelityPageView {
  page_id: string;
  page_index: number;
  level: FidelityLevel;
  renderer: string;
  preview_path?: string | null;
  downgrade_reason?: string | null;
  scene: {
    shapes: Array<{ shape_id: string; name: string; kind: string; text: string }>;
    motion_cues: MotionCueView[];
  };
}

interface FidelityWorkspaceProps {
  pages: FidelityPageView[];
  selectedPageId?: string;
  onSelectPage: (pageId: string) => void;
  onRecapture: (pageId: string) => void;
}

const levelLabels: Record<FidelityLevel, string> = {
  F0: '兼容静态',
  F1: '高保真静态',
  F2: '可解释动画',
  F3: '原生捕获',
};

export function FidelityWorkspace({
  pages,
  selectedPageId,
  onSelectPage,
  onRecapture,
}: FidelityWorkspaceProps) {
  const selected = pages.find((page) => page.page_id === selectedPageId) ?? pages[0];

  return (
    <section className="fidelity-workspace" aria-label="PPT 高保真与元素级动画">
      <div className="fidelity-heading">
        <div>
          <h3>PPT 高保真与元素级动画</h3>
          <p className="muted">按页面查看渲染等级、元素语义和动画映射降级原因。</p>
        </div>
        <span className="fidelity-count">{pages.length} 页</span>
      </div>
      <div className="fidelity-layout">
        <nav className="fidelity-pages" aria-label="PPT 页面列表">
          {pages.map((page) => (
            <button
              className={
                page.page_id === selected?.page_id ? 'fidelity-page selected' : 'fidelity-page'
              }
              key={page.page_id}
              onClick={() => onSelectPage(page.page_id)}
            >
              <strong>第 {page.page_index} 页</strong>
              <span>
                {page.level} · {levelLabels[page.level]}
              </span>
            </button>
          ))}
        </nav>
        {selected ? (
          <article className="fidelity-detail">
            <div className="fidelity-detail-heading">
              <div>
                <h4>
                  第 {selected.page_index} 页 · {levelLabels[selected.level]}
                </h4>
                <p className="muted">Renderer: {selected.renderer}</p>
              </div>
              <button className="secondary" onClick={() => onRecapture(selected.page_id)}>
                重新处理此页
              </button>
            </div>
            {selected.downgrade_reason && (
              <div className="warning">降级原因：{selected.downgrade_reason}</div>
            )}
            <div className="fidelity-elements">
              <h5>元素 {selected.scene.shapes.length} 个</h5>
              <ul>
                {selected.scene.shapes.map((shape) => (
                  <li key={shape.shape_id}>
                    <strong>{shape.name}</strong>
                    <span>
                      {shape.kind} · {shape.text || '无文本'}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="fidelity-motion">
              <h5>动画映射 {selected.scene.motion_cues.length} 个</h5>
              <ul>
                {selected.scene.motion_cues.map((cue) => (
                  <li key={cue.cue_id}>
                    <strong>{cue.entrance || 'effect'}</strong>
                    <span>
                      {cue.support} · {cue.duration_ms}ms
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          </article>
        ) : (
          <p className="muted">尚未生成高保真清单。</p>
        )}
      </div>
    </section>
  );
}
