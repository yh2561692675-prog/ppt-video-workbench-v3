import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../../api/client';

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function UpdatePanel() {
  const queryClient = useQueryClient();
  const state = useQuery({ queryKey: ['update-state'], queryFn: api.updateState });
  const candidate = useQuery({ queryKey: ['update-candidate'], queryFn: api.checkUpdate });
  const stage = useMutation({
    mutationFn: api.stageUpdate,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['update-state'] }),
  });
  const apply = useMutation({
    mutationFn: api.applyUpdate,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['update-state'] });
      void queryClient.invalidateQueries({ queryKey: ['update-candidate'] });
    },
  });
  const rollback = useMutation({
    mutationFn: api.rollbackUpdate,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['update-state'] }),
  });
  const stagedVersion = stage.data?.staged_version ?? state.data?.staged_version;
  const appliedVersion = apply.data?.current_version;
  const availableUpdate = candidate.data;

  return (
    <section className="llm-settings update-panel">
      <div className="update-summary">
        <strong>当前版本：{state.data?.current_version ?? '读取中…'}</strong>
        <span className="muted">仅检查和应用 stable 更新，不会上传项目内容。</span>
      </div>
      {availableUpdate ? (
        <div className="update-card">
          <strong>可用 stable 更新：{availableUpdate.version}</strong>
          <span>{availableUpdate.notes || '此版本没有额外说明。'}</span>
          <span className="muted">下载大小：{formatBytes(availableUpdate.size)}</span>
          <button
            className="secondary"
            type="button"
            disabled={stage.isPending || Boolean(stagedVersion)}
            onClick={() => stage.mutate(availableUpdate.package_relative_path)}
          >
            {stagedVersion ? `已暂存 ${stagedVersion}` : '下载并暂存'}
          </button>
        </div>
      ) : (
        <p className="muted">当前没有可用 stable 更新。</p>
      )}
      {stagedVersion ? (
        <div className="update-card update-card-confirm">
          <strong>更新包已校验并准备就绪</strong>
          <span>应用前会备份设置与工作区索引，失败时自动恢复上一版本。</span>
          <button
            className="primary"
            type="button"
            disabled={apply.isPending}
            onClick={() => {
              if (window.confirm(`确认应用 ${stagedVersion}？`)) apply.mutate();
            }}
          >
            确认应用更新
          </button>
        </div>
      ) : null}
      {state.data?.previous_version ? (
        <button
          className="secondary"
          type="button"
          disabled={rollback.isPending}
          onClick={() => {
            if (window.confirm(`确认回滚到 ${state.data?.previous_version}？`)) rollback.mutate();
          }}
        >
          回滚到上一版本
        </button>
      ) : null}
      {appliedVersion ? <p className="success">已应用 {appliedVersion}</p> : null}
      {apply.error ? <p className="error">{apply.error.message}</p> : null}
      {stage.error ? <p className="error">{stage.error.message}</p> : null}
      {rollback.error ? <p className="error">{rollback.error.message}</p> : null}
      {state.error || candidate.error ? <p className="error">暂时无法读取更新状态</p> : null}
    </section>
  );
}
