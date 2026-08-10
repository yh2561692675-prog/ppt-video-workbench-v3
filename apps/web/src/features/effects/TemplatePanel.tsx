export type EffectAspectRatio = '16:9' | '9:16';
export type EffectBackground =
  | 'tech_blue'
  | 'risk_red'
  | 'warm_gold'
  | 'paper_grid'
  | 'regional_teal';

export interface TemplatePanelValue {
  template: string;
  background: EffectBackground;
  aspectRatio: EffectAspectRatio;
  manualLock: boolean;
}

export function TemplatePanel({
  template,
  background,
  aspectRatio,
  manualLock,
  onChange,
}: TemplatePanelValue & { onChange: (value: TemplatePanelValue) => void }) {
  return (
    <section className="effect-template-panel" aria-label="特效模板控制">
      <h3>模板与画幅</h3>
      <label>
        特效模板
        <select
          aria-label="特效模板"
          value={template}
          onChange={(event) =>
            onChange({ template: event.target.value, background, aspectRatio, manualLock })
          }
        >
          <option value="SafeSlide">SafeSlide</option>
          <option value="ProgressiveReveal">ProgressiveReveal</option>
          <option value="FocusSpotlight">FocusSpotlight</option>
          <option value="ChapterCurtain">ChapterCurtain</option>
          <option value="ChartNarration">ChartNarration</option>
          <option value="CompareMode">CompareMode</option>
        </select>
      </label>
      <label>
        语义背景
        <select
          aria-label="语义背景"
          value={background}
          onChange={(event) =>
            onChange({
              template,
              background: event.target.value as EffectBackground,
              aspectRatio,
              manualLock,
            })
          }
        >
          <option value="tech_blue">科技蓝</option>
          <option value="risk_red">风险红</option>
          <option value="warm_gold">暖金</option>
          <option value="paper_grid">纸张网格</option>
          <option value="regional_teal">区域青</option>
        </select>
      </label>
      <label>
        画幅
        <select
          aria-label="画幅"
          value={aspectRatio}
          onChange={(event) =>
            onChange({
              template,
              background,
              aspectRatio: event.target.value as EffectAspectRatio,
              manualLock,
            })
          }
        >
          <option value="16:9">横屏 16:9</option>
          <option value="9:16">竖屏 9:16</option>
        </select>
      </label>
      <label>
        <input
          type="checkbox"
          aria-label="人工锁定模板"
          checked={manualLock}
          onChange={(event) =>
            onChange({ template, background, aspectRatio, manualLock: event.target.checked })
          }
        />
        人工锁定模板
      </label>
    </section>
  );
}
