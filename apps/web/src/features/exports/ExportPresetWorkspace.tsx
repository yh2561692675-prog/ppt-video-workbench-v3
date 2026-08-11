import { useState } from 'react';

import type { ExportPlanRecord, ExportPresetRecord } from '../../api/client';

interface ExportPresetWorkspaceProps {
  presets: ExportPresetRecord[];
  plans: ExportPlanRecord[];
  onCreatePlan: (presetId: string) => void;
}

export function ExportPresetWorkspace({
  presets,
  plans,
  onCreatePlan,
}: ExportPresetWorkspaceProps) {
  const [selectedPreset, setSelectedPreset] = useState(presets[0]?.id ?? '');
  return (
    <section className="export-preset-workspace" aria-label="多规格导出">
      <div className="export-preset-heading">
        <div>
          <h3>多规格导出</h3>
          <p className="muted">统一生成横屏、竖屏、方屏、GIF 与平台切片计划。</p>
        </div>
        <div className="export-preset-actions">
          <select
            aria-label="导出预设"
            value={selectedPreset}
            onChange={(event) => setSelectedPreset(event.target.value)}
          >
            {presets.map((preset) => (
              <option value={preset.id} key={preset.id}>
                {preset.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="primary"
            disabled={!selectedPreset}
            onClick={() => onCreatePlan(selectedPreset)}
          >
            生成导出计划
          </button>
        </div>
      </div>
      <div className="export-preset-grid">
        {presets.map((preset) => (
          <button
            type="button"
            className={`export-preset-card${preset.id === selectedPreset ? ' selected' : ''}`}
            key={preset.id}
            onClick={() => setSelectedPreset(preset.id)}
          >
            <strong>{preset.label}</strong>
            <span>
              {preset.width}×{preset.height} · {preset.fps}fps · {preset.container.toUpperCase()}
            </span>
            <small>
              {preset.video_bitrate} ·{' '}
              {preset.max_segment_seconds ? `${preset.max_segment_seconds}s 分片` : '不分片'}
            </small>
          </button>
        ))}
      </div>
      <div className="export-plan-list">
        <h4>已生成计划</h4>
        {plans.length === 0 ? (
          <p className="muted">尚未生成导出计划。</p>
        ) : (
          plans.map((plan) => (
            <div className="export-plan-row" key={plan.plan_id}>
              <strong>{plan.preset.label}</strong>
              <span>{plan.output_relative_path}</span>
              <span className="muted">Revision {plan.revision}</span>
              {plan.segment_paths.length > 0 && <span>{plan.segment_paths.length} 个切片</span>}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
