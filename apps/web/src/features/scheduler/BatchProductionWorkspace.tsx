import { useState } from 'react';

import type { BatchProductionRecord } from '../../api/client';

interface BatchProductionWorkspaceProps {
  batches: BatchProductionRecord[];
  presetIds: string[];
  onCreate: (payload: Record<string, unknown>) => void;
  onDispatch: (batchId: string, allowNight: boolean) => void;
  onRerun: (batchId: string, itemIds: string[]) => void;
}

export function BatchProductionWorkspace({
  batches,
  presetIds,
  onCreate,
  onDispatch,
  onRerun,
}: BatchProductionWorkspaceProps) {
  const [selectedPreset, setSelectedPreset] = useState(presetIds[0] ?? '');
  const [nightQueue, setNightQueue] = useState(false);
  const latest = batches.at(-1);
  return (
    <section className="batch-production-workspace" aria-label="批量生产与资源调度">
      <div className="batch-heading">
        <div>
          <h3>批量生产与资源调度</h3>
          <p className="muted">按优先级、依赖关系和 CPU/GPU/内存限额排队渲染。</p>
        </div>
        <div className="batch-actions">
          <select
            aria-label="批量导出预设"
            value={selectedPreset}
            onChange={(event) => setSelectedPreset(event.target.value)}
          >
            {presetIds.map((presetId) => (
              <option value={presetId} key={presetId}>
                {presetId}
              </option>
            ))}
          </select>
          <label className="batch-night-toggle">
            <input
              type="checkbox"
              checked={nightQueue}
              onChange={(event) => setNightQueue(event.target.checked)}
            />
            夜间队列
          </label>
          <button
            type="button"
            className="primary"
            disabled={!selectedPreset}
            onClick={() =>
              onCreate({
                preset_ids: [selectedPreset],
                night_queue: nightQueue,
                priority: 60,
                resource_limits: {
                  max_parallel: 2,
                  cpu_cores: 8,
                  memory_mb: 16_384,
                  gpu_slots: 1,
                  per_job_memory_mb: 4_096,
                },
              })
            }
          >
            创建批次
          </button>
        </div>
      </div>
      {latest ? (
        <div className="batch-latest">
          <div className="batch-latest-heading">
            <strong>批次 {latest.batch_id.slice(0, 8)}</strong>
            <span className={`batch-status batch-status-${latest.status}`}>{latest.status}</span>
            <button
              type="button"
              className="secondary"
              onClick={() => onDispatch(latest.batch_id, nightQueue)}
            >
              调度可运行任务
            </button>
          </div>
          <div className="batch-resource-summary">
            并行 {latest.resource_limits.max_parallel} · CPU {latest.resource_limits.cpu_cores} 核 ·
            内存 {latest.resource_limits.memory_mb} MB · GPU {latest.resource_limits.gpu_slots}
          </div>
          <div className="batch-item-list">
            {latest.items.map((item) => (
              <div className="batch-item-row" key={item.item_id}>
                <span>{item.preset_id}</span>
                <span>优先级 {item.priority}</span>
                <span className={`batch-item-status batch-item-status-${item.status}`}>
                  {item.status}
                </span>
                {item.error && <small className="error">{item.error}</small>}
                {item.status === 'failed' && (
                  <button
                    type="button"
                    className="secondary"
                    onClick={() => onRerun(latest.batch_id, [item.item_id])}
                  >
                    重跑
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="muted">暂无批量生产批次。</p>
      )}
    </section>
  );
}
