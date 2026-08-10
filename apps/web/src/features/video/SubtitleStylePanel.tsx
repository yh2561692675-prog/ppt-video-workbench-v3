interface SubtitleStylePanelProps {
  reducedMotion: boolean;
  onReducedMotionChange: (value: boolean) => void;
}

export function SubtitleStylePanel({
  reducedMotion,
  onReducedMotionChange,
}: SubtitleStylePanelProps) {
  return (
    <section className="subtitle-style-panel" aria-label="字幕样式">
      <h3>字幕与动画</h3>
      <label>
        <input
          type="checkbox"
          checked={reducedMotion}
          onChange={(event) => onReducedMotionChange(event.target.checked)}
        />
        减少动态效果
      </label>
      <p className="muted">字幕使用底部安全区；发生遮挡时会自动切换位置或启用半透明底板。</p>
    </section>
  );
}
