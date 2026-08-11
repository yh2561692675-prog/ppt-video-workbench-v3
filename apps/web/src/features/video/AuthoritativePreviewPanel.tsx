import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';

import { api, type RenderGraphV2Record } from '../../api/client';

interface AuthoritativePreviewPanelProps {
  projectId: string;
  graph: RenderGraphV2Record;
}

const TERMINAL_STATUSES = new Set(['succeeded', 'failed', 'cancelled']);

export function AuthoritativePreviewPanel({ projectId, graph }: AuthoritativePreviewPanelProps) {
  const durationSeconds = graph.duration_us / 1_000_000;
  const [startSeconds, setStartSeconds] = useState(0);
  const [endSeconds, setEndSeconds] = useState(Math.min(durationSeconds, 10));
  const [jobId, setJobId] = useState<string | null>(null);
  const graphHash = graph.graph_hash ?? graph.content_hash ?? '';
  const rangeValid =
    graphHash.length === 64 && endSeconds > startSeconds && endSeconds <= durationSeconds;
  const submit = useMutation({
    mutationFn: () =>
      api.createAuthoritativePreview(projectId, graph.graph_id, {
        graph_id: graph.graph_id,
        graph_hash: graphHash,
        start_us: Math.round(startSeconds * 1_000_000),
        end_us: Math.round(endSeconds * 1_000_000),
        runtime_version: 'rendergraph-v2',
      }),
    onSuccess: (job) => setJobId(job.id),
  });
  const job = useQuery({
    queryKey: ['authoritative-preview-job', projectId, jobId],
    queryFn: () => api.getDurableJob(projectId, jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.job.status;
      return status && TERMINAL_STATUSES.has(status) ? false : 1000;
    },
  });
  const record = job.data?.job;
  const manifest = record?.result?.manifest;
  const videoUrl = manifest ? projectAssetUrl(projectId, manifest.video_relative_path) : null;

  return (
    <section className="authoritative-preview-panel" aria-label="权威区间预览">
      <div>
        <h4>权威区间预览</h4>
        <p className="muted">
          由持久化 Worker 使用与最终导出相同的 RenderGraph、Remotion 和 FFmpeg 链路生成。
        </p>
      </div>
      <dl className="preview-diagnostics" aria-label="预览一致性诊断">
        <div>
          <dt>Graph</dt>
          <dd>{graphHash.slice(0, 12)}</dd>
        </div>
        <div>
          <dt>Timeline revision</dt>
          <dd>{graph.timeline_revision}</dd>
        </div>
        <div>
          <dt>受影响区间</dt>
          <dd>{graph.affected_ranges.length}</dd>
        </div>
        {manifest && (
          <div>
            <dt>Cache key</dt>
            <dd>{manifest.cache_key.slice(0, 12)}</dd>
          </div>
        )}
      </dl>
      <dl className="preview-diagnostics" aria-label="预览一致性诊断">
        <div>
          <dt>Graph</dt>
          <dd>{graphHash.slice(0, 12)}</dd>
        </div>
        <div>
          <dt>Timeline revision</dt>
          <dd>{graph.timeline_revision}</dd>
        </div>
        <div>
          <dt>受影响区间</dt>
          <dd>{graph.affected_ranges.length}</dd>
        </div>
        {manifest && (
          <div>
            <dt>Cache key</dt>
            <dd>{manifest.cache_key.slice(0, 12)}</dd>
          </div>
        )}
      </dl>
      <div className="authoritative-preview-range">
        <label>
          开始（秒）
          <input
            aria-label="权威预览开始时间"
            type="number"
            min={0}
            max={durationSeconds}
            step="0.1"
            value={startSeconds}
            onChange={(event) => setStartSeconds(Number(event.target.value))}
          />
        </label>
        <label>
          结束（秒）
          <input
            aria-label="权威预览结束时间"
            type="number"
            min={0}
            max={durationSeconds}
            step="0.1"
            value={endSeconds}
            onChange={(event) => setEndSeconds(Number(event.target.value))}
          />
        </label>
        <button
          className="primary"
          disabled={!rangeValid || submit.isPending}
          onClick={() => submit.mutate()}
        >
          {submit.isPending ? '正在提交…' : '生成权威预览'}
        </button>
      </div>
      {!rangeValid && <p className="warning">结束时间必须晚于开始时间且不能超出成片。</p>}
      {record && (
        <p className={record.status === 'failed' ? 'warning' : 'muted'}>
          任务 {record.status} · {Math.round(record.progress * 100)}% · {record.stage}
          {record.error ? ` · ${record.error}` : ''}
        </p>
      )}
      {submit.isError && <p className="warning">权威预览提交失败，请检查预检阻断项。</p>}
      {job.isError && <p className="warning">暂时无法读取权威预览任务状态。</p>}
      {videoUrl && manifest && (
        <div className="authoritative-preview-result">
          <video controls src={videoUrl} aria-label="权威预览成片" />
          <small>
            {manifest.duration_us / 1_000_000}s · {manifest.container} · 字幕{' '}
            {manifest.subtitle_mode} · {manifest.video_hash.slice(0, 12)}
          </small>
        </div>
      )}
    </section>
  );
}

function projectAssetUrl(projectId: string, relativePath: string): string {
  return `/api/projects/${projectId}/video/assets/${relativePath
    .split('/')
    .map(encodeURIComponent)
    .join('/')}`;
}
