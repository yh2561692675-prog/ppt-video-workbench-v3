import { useState } from 'react';

import { api, type CleanupPlan, type CleanupResult } from '../../../api/client';

interface StoragePanelProps {
  projectId: string;
}

export function StoragePanel({ projectId }: StoragePanelProps) {
  const [plan, setPlan] = useState<CleanupPlan | null>(null);
  const [result, setResult] = useState<CleanupResult | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function estimate() {
    setBusy(true);
    setError(null);
    setResult(null);
    setConfirmed(false);
    try {
      setPlan(await api.estimateCleanup(projectId));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '缓存估算失败');
    } finally {
      setBusy(false);
    }
  }

  async function execute() {
    if (!plan || !confirmed) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.executeCleanup(projectId, plan.id, plan.confirmation_token));
      setPlan(null);
      setConfirmed(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '缓存清理失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="storage-panel" aria-label="缓存管理">
      <div className="storage-heading">
        <h3>缓存管理</h3>
        <button className="secondary" type="button" onClick={estimate} disabled={busy}>
          估算可清理缓存
        </button>
      </div>
      {error ? <p className="error">{error}</p> : null}
      {plan ? (
        <div className="storage-estimate">
          <p>
            可释放 <strong>{formatBytes(plan.bytes_reclaimable)}</strong>，影响节点：{' '}
            {plan.affected_nodes.join('、') || '无'}
          </p>
          <p className="muted">下一次操作将按依赖重建。</p>
          <p className="muted">
            受保护：{plan.protected_paths.slice(0, 4).join('、') || '项目源数据'}
          </p>
          <label className="storage-confirm">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(event) => setConfirmed(event.target.checked)}
            />
            我确认删除可重建缓存
          </label>
          <button className="danger" type="button" onClick={execute} disabled={!confirmed || busy}>
            确认并清理
          </button>
        </div>
      ) : null}
      {result ? <p className="success">已释放 {formatBytes(result.bytes_reclaimed)}</p> : null}
    </section>
  );
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}
