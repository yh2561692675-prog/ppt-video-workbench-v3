export type RhythmProfile = 'steady' | 'standard' | 'compact' | 'enhanced';

export interface RhythmPanelValue {
  profile: RhythmProfile;
  strength: number;
}

export function RhythmPanel({
  profile,
  strength,
  onChange,
}: RhythmPanelValue & { onChange: (value: RhythmPanelValue) => void }) {
  return (
    <section className="effect-rhythm-panel" aria-label="特效节奏控制">
      <h3>节奏</h3>
      <label>
        节奏档位
        <select
          aria-label="节奏档位"
          value={profile}
          onChange={(event) => onChange({ profile: event.target.value as RhythmProfile, strength })}
        >
          <option value="steady">平稳</option>
          <option value="standard">标准</option>
          <option value="compact">紧凑</option>
          <option value="enhanced">增强</option>
        </select>
      </label>
      <label>
        特效强度
        <input
          aria-label="特效强度"
          type="range"
          min="0"
          max="1"
          step="0.1"
          value={strength}
          onChange={(event) => onChange({ profile, strength: Number(event.target.value) })}
        />
        <output>{Math.round(strength * 100)}%</output>
      </label>
    </section>
  );
}
