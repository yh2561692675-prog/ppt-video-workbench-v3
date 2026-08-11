import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, ApiRequestError, type DurableJobRecord } from '../../api/client';

const TERMINAL = new Set(['succeeded', 'failed', 'cancelled', 'needs_confirmation']);

export function TaskCenter({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const jobs = useQuery({
    queryKey: ['durable-jobs', projectId],
    queryFn: () => api.listDurableJobs(projectId),
    refetchInterval: (query) =>
      query.state.data?.some((job) => !TERMINAL.has(job.status)) ? 1000 : false,
  });
  const action = useMutation({
    mutationFn: ({
      job,
      kind,
    }: {
      job: DurableJobRecord;
      kind: 'pause' | 'resume' | 'cancel' | 'confirm_retry';
    }) =>
      api.actDurableJob(projectId, job.id, {
        action: kind,
        expected_revision: job.revision,
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData<DurableJobRecord[]>(['durable-jobs', projectId], (current) =>
        (current ?? []).map((job) => (job.id === updated.id ? updated : job)),
      );
    },
    onError: (error) => {
      if (error instanceof ApiRequestError && error.status === 409) void jobs.refetch();
    },
  });

  return (
    <section className="task-center" aria-label="后台任务中心">
      <div className="timeline-heading">
        <div>
          <h3>后台任务中心</h3>
          <p className="muted">渲染、预览与素材处理任务均由持久化队列统一管理。</p>
        </div>
        <button
          className="secondary"
          onClick={() => void jobs.refetch()}
          disabled={jobs.isFetching}
        >
          刷新
        </button>
      </div>
      <div aria-live="polite">
        {jobs.isLoading && <p className="muted">正在加载任务…</p>}
        {jobs.isError && <p className="warning">任务列表暂时无法读取。</p>}
        {action.isError && <p className="warning">任务状态已变化，列表已刷新，请重试操作。</p>}
        {jobs.data?.length === 0 && <p className="muted">当前没有后台任务。</p>}
      </div>
      <div className="task-center-list">
        {jobs.data?.map((job) => (
          <article className="task-center-item" key={job.id}>
            <div>
              <strong>{job.job_type}</strong>
              <small className="muted">
                {' '}
                {job.stage || 'queued'} · revision {job.revision}
              </small>
              <p>{job.message || job.error || job.status}</p>
            </div>
            <div>
              <progress value={job.progress} max={1} aria-label={`${job.job_type} 进度`} />
              <span>
                {' '}
                {Math.round(job.progress * 100)}% · {job.status}
              </span>
            </div>
            <div className="timeline-actions">
              {job.status === 'running' && (
                <button className="secondary" onClick={() => action.mutate({ job, kind: 'pause' })}>
                  暂停
                </button>
              )}
              {job.status === 'paused' && (
                <button
                  className="secondary"
                  onClick={() => action.mutate({ job, kind: 'resume' })}
                >
                  继续
                </button>
              )}
              {job.status === 'needs_confirmation' && (
                <button
                  className="secondary"
                  onClick={() => action.mutate({ job, kind: 'confirm_retry' })}
                >
                  确认后重试
                </button>
              )}
              {!TERMINAL.has(job.status) && (
                <button
                  className="secondary"
                  onClick={() => action.mutate({ job, kind: 'cancel' })}
                >
                  取消
                </button>
              )}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
