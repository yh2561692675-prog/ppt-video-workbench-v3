import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api, type Project } from '../../api/client';
import { QualityWorkspace } from './QualityWorkspace';

export function QualityPanel({ project }: { project: Project }) {
  const queryClient = useQueryClient();
  const latestQuery = useQuery({
    queryKey: ['quality-latest', project.id],
    queryFn: () => api.latestQualityJob(project.id),
    retry: false,
    refetchInterval: (query) => (query.state.data?.status === 'running' ? 1000 : false),
  });
  const createMutation = useMutation({
    mutationFn: () => {
      const exportRecord = project.video_export;
      if (!exportRecord) throw new Error('请先完成一次渲染导出');
      return api.createQualityJob(project.id, {
        video_path: exportRecord.mp4_relative_path,
        expected_duration_ms: exportRecord.duration_ms,
      });
    },
    onSuccess: (result) => queryClient.setQueryData(['quality-latest', project.id], result),
  });
  const issueActionMutation = useMutation({
    mutationFn: ({ issueId, action }: { issueId: string; action: 'confirm' | 'retry' }) => {
      const jobId = latestQuery.data?.job_id;
      if (!jobId) throw new Error('质量任务不存在');
      return api.qualityIssueAction(project.id, jobId, issueId, action);
    },
    onSuccess: (result) => queryClient.setQueryData(['quality-latest', project.id], result),
  });
  const report = latestQuery.data?.report ?? null;
  return (
    <QualityWorkspace
      projectId={project.id}
      report={report}
      onRun={() => createMutation.mutate()}
      onRetry={(issueId) => issueActionMutation.mutate({ issueId, action: 'retry' })}
      onConfirm={(issueId) => issueActionMutation.mutate({ issueId, action: 'confirm' })}
    />
  );
}
