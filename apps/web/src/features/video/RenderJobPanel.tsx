import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, RenderJob, RenderJobStatus } from '../../api/client';
import { renderJobPollInterval } from './renderJobPolling';

export function RenderJobPanel({ projectId, enabled = true }: { projectId: string; enabled?: boolean }) {
  const queryClient = useQueryClient();
  const jobQuery = useQuery<{ job: RenderJob } | null>({
    queryKey: ['render-job-current', projectId],
    queryFn: () => api.getCurrentRenderJob(projectId),
    enabled,
    refetchInterval: (query) => renderJobPollInterval(query.state.data?.job),
    refetchOnWindowFocus: true,
  });
  const createMutation = useMutation({
    mutationFn: () => api.createRenderJob(projectId),
    onSuccess: (result) => queryClient.setQueryData(['render-job-current', projectId], { job: result.job }),
  });
  const actionMutation = useMutation({
    mutationFn: ({ jobId, action }: { jobId: string; action: 'pause' | 'resume' | 'cancel' | 'retry' }) =>
      api.actOnRenderJob(projectId, jobId, action),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['render-job-current', projectId] }),
  });
  const job = jobQuery.data?.job;
  if (!enabled) return null;
  if (!job) {
    return (
      <section className="video-render-panel" aria-label="渲染与导出">
        <p className="muted">完整预检通过后，可以异步开始最终渲染。</p>
        <button className="primary" onClick={() => createMutation.mutate()} disabled={createMutation.isPending}>
          {createMutation.isPending ? '正在提交…' : '开始渲染与导出'}
        </button>
        {createMutation.isError && <p className="error">提交渲染任务失败，请检查预检结果后重试。</p>}
      </section>
    );
  }
  const action = (name: 'pause' | 'resume' | 'cancel' | 'retry') =>
    actionMutation.mutate({ jobId: job.id, action: name });
  return (
    <section className="video-render-panel" aria-label="渲染与导出">
      <div className="render-job-meta">
        <span className="status-pill">{statusLabel(job.status)}</span>
        <span className="muted">{job.stage}</span>
      </div>
      <p aria-live="polite">{job.message}</p>
      <progress className="render-job-progress" max={1} value={job.progress} aria-label="渲染进度" />
      <div className="render-job-meta">
        <span>{Math.round(job.progress * 100)}%</span>
        <span>尝试 {job.attempts}/{job.max_attempts}</span>
      </div>
      <div className="render-job-actions">
        {['queued', 'running', 'pause_requested'].includes(job.status) && (
          <button className="secondary" onClick={() => action('pause')}>暂停</button>
        )}
        {job.status === 'paused' && <button className="primary" onClick={() => action('resume')}>继续</button>}
        {['queued', 'running', 'pause_requested', 'paused'].includes(job.status) && (
          <button className="secondary" onClick={() => action('cancel')}>取消</button>
        )}
        {['failed', 'cancelled'].includes(job.status) && (
          <button className="primary" onClick={() => action('retry')}>重试</button>
        )}
      </div>
      {job.error_code && <p className="error">错误代码：{job.error_code}</p>}
      {job.result && (
        <p className="success">制作包已生成：{job.result.package_relative_path}</p>
      )}
    </section>
  );
}

function statusLabel(status: RenderJobStatus): string {
  const labels: Record<RenderJobStatus, string> = {
    queued: '排队中', running: '渲染中', pause_requested: '等待暂停', paused: '已暂停',
    cancel_requested: '等待取消', succeeded: '已完成', failed: '失败', cancelled: '已取消',
  };
  return labels[status];
}
