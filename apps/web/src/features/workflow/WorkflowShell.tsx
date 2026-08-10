import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { api, Project } from '../../api/client';
import { AudioImport } from '../audio/import/AudioImport';
import { AudioPipelineActions } from '../audio/import/AudioPipelineActions';
import { AudioDifferences } from '../audio/differences/AudioDifferences';
import { AudioGatePanel } from '../audio/gate/AudioGatePanel';
import { HeyGenAudioPanel } from '../audio/heygen/HeyGenAudioPanel';
import { AudioTimeline } from '../audio/timeline/AudioTimeline';
import { MaterialImport } from '../import/MaterialImport';
import { MatchingWorkspace } from '../matching/MatchingWorkspace';
import { NarrationWorkspace } from '../narration/editor/NarrationWorkspace';
import { PreflightWorkspace } from '../preflight/PreflightWorkspace';
import { SubtitleActions } from '../subtitles/SubtitleActions';
import { PreviewWorkspace } from '../video/PreviewWorkspace';
import { EffectWorkspace } from '../effects/EffectWorkspace';
import { RenderJobPanel } from '../video/RenderJobPanel';

const STEPS = [
  '新建项目',
  '导入材料',
  '材料解析与匹配',
  '逐页旁白校对',
  '配音与音频对齐',
  '效果预览与完整预检',
  '渲染与导出',
];

export function WorkflowShell() {
  const { projectId = '' } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const projectQuery = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => api.getProject(projectId),
    enabled: Boolean(projectId),
  });
  const disk = useQuery({ queryKey: ['disk'], queryFn: api.disk });
  const audioGateQuery = useQuery({
    queryKey: ['audio-gate', projectId],
    queryFn: () => api.audioGate(projectId),
    enabled: Boolean(projectId),
  });
  const videoPreflightQuery = useQuery({
    queryKey: ['video-preflight', projectId],
    queryFn: () => api.videoPreflight(projectId),
    enabled: Boolean(projectId) && (projectQuery.data?.current_step ?? 0) >= 6,
  });
  const preflightQuery = useQuery({
    queryKey: ['preflight', projectId],
    queryFn: () => api.getPreflight(projectId),
    enabled: Boolean(projectId) && (projectQuery.data?.current_step ?? 0) >= 6,
  });
  const [selectedAudioRoute, setSelectedAudioRoute] = useState<AudioRoute>(null);
  const persistedAudioRoute = inferAudioRoute(projectQuery.data);
  const audioRoute = selectedAudioRoute ?? persistedAudioRoute;
  const audioRouteRef = useRef<AudioRoute>(audioRoute);
  audioRouteRef.current = audioRoute;

  function claimAudioRoute(route: Exclude<AudioRoute, null>): boolean {
    const current = audioRouteRef.current;
    if (current !== null && current !== route) return false;
    audioRouteRef.current = route;
    setSelectedAudioRoute(route);
    return true;
  }

  function accept(project: Project) {
    queryClient.setQueryData(['project', projectId], project);
    navigate(`/projects/${project.id}/step/${project.current_step}`, { replace: true });
  }

  function refreshAudioState() {
    void projectQuery.refetch();
    void queryClient.invalidateQueries({ queryKey: ['audio-gate', projectId] });
  }

  function refreshVideoState() {
    void projectQuery.refetch();
    void videoPreflightQuery.refetch();
    void preflightQuery.refetch();
  }

  const stepMutation = useMutation({
    mutationFn: (step: number) => api.setStep(projectId, step),
    onSuccess: accept,
  });
  const createRenderJobMutation = useMutation({
    mutationFn: () => api.createRenderJob(projectId),
    onSuccess: () => navigate(`/projects/${projectId}/step/7`),
  }) as unknown as {
    mutate: () => void;
    isPending: boolean;
    isError: boolean;
    data: { job: { id: string } };
  };
  const videoPreflightMutation = useMutation({
    mutationFn: (settings: { reduced_motion: boolean }) => api.videoPreflight(projectId, settings),
    onSuccess: (result) => {
      queryClient.setQueryData(['video-preflight', projectId], result);
      void projectQuery.refetch();
    },
  });
  const preflightMutation = useMutation({
    mutationFn: () => api.preflight(projectId),
    onSuccess: (result) => queryClient.setQueryData(['preflight', projectId], result),
  });
  const preflightConfirmMutation = useMutation({
    mutationFn: ({ issueId, actor, note }: { issueId: string; actor: string; note: string }) =>
      api.confirmPreflightIssue(projectId, issueId, actor, note),
    onSuccess: (result) => queryClient.setQueryData(['preflight', projectId], result),
  });
  const pauseMutation = useMutation({ mutationFn: () => api.pause(projectId), onSuccess: accept });
  const resumeMutation = useMutation({
    mutationFn: () => api.resume(projectId),
    onSuccess: accept,
  });
  const project = projectQuery.data;

  if (projectQuery.isLoading) return <main className="page">项目加载中……</main>;
  if (!project) return <main className="page error">项目无法打开。</main>;

  const paused = project.status === 'paused';
  const legacyRenderPanelEnabled = false;
  const subtitlesUnlocked = audioGateQuery.data?.allowed === true;
  const pageLabels = Object.fromEntries(
    project.pages.map((page) => [page.id, `第${page.order}页`]),
  );
  return (
    <main className="page">
      <header className="topbar">
        <div>
          <Link className="eyebrow" to="/">
            返回项目中心
          </Link>
          <h1>{project.name}</h1>
        </div>
        <div className="status-row">
          <span className="muted">
            {disk.data ? `可用磁盘 ${formatBytes(disk.data.free)}` : '磁盘检测中'}
          </span>
          <span className="status-pill">{paused ? '已暂停' : '进行中'}</span>
          <button
            className="secondary"
            onClick={() => (paused ? resumeMutation.mutate() : pauseMutation.mutate())}
          >
            {paused ? '继续项目' : '暂停项目'}
          </button>
        </div>
      </header>

      <div className="workflow-grid">
        <nav className="steps" aria-label="制作步骤">
          {STEPS.map((label, index) => {
            const step = index + 1;
            return (
              <button
                className="step"
                key={label}
                aria-current={project.current_step === step ? 'step' : undefined}
                disabled={
                  paused ||
                  stepMutation.isPending ||
                  (step >= 6 && !subtitlesUnlocked) ||
                  (step === 7 && preflightQuery.data?.allowed !== true)
                }
                onClick={() => stepMutation.mutate(step)}
              >
                第{step}步 {label}
              </button>
            );
          })}
        </nav>
        <section className="stage">
          <div className="eyebrow">STEP {project.current_step}</div>
          <h2>{STEPS[project.current_step - 1]}</h2>
          <p className="muted" style={{ marginTop: 14 }}>
            当前项目目录：{project.project_dir}
          </p>
          {project.current_step === 2 && (
            <MaterialImport projectId={project.id} initialSources={project.source_files ?? []} />
          )}
          {project.current_step === 3 && (
            <MatchingWorkspace projectId={project.id} initialMatches={project.matches ?? []} />
          )}
          {project.current_step === 4 && (
            <NarrationWorkspace
              projectId={project.id}
              pages={project.pages ?? []}
              extractions={project.page_extractions ?? []}
              matches={project.matches ?? []}
            />
          )}
          {project.current_step === 5 && (
            <>
              <AudioImport
                projectId={project.id}
                initialAudio={project.audio_import ?? null}
                disabled={audioRoute === 'heygen'}
                disabledReason="HeyGen 页面配音路线已启用，不能同时导入本地录音。"
                onImported={() => claimAudioRoute('local')}
              />
              <HeyGenAudioPanel
                projectId={project.id}
                pages={project.pages}
                localAudioActive={audioRoute === 'local'}
                isLocalAudioActive={() => audioRouteRef.current === 'local'}
                onStarted={() => claimAudioRoute('heygen')}
                onChanged={refreshAudioState}
              />
              <AudioPipelineActions projectId={project.id} onChanged={refreshAudioState} />
              <AudioGatePanel gate={audioGateQuery.data ?? null} pageLabels={pageLabels} />
              <SubtitleActions
                projectId={project.id}
                allowed={subtitlesUnlocked}
                onChanged={refreshVideoState}
              />
              <AudioDifferences
                projectId={project.id}
                differences={project.audio_differences ?? []}
                onChanged={refreshAudioState}
              />
              {project.audio_timeline && (
                <AudioTimeline
                  projectId={project.id}
                  initialTimeline={project.audio_timeline}
                  onChanged={refreshAudioState}
                />
              )}
            </>
          )}
          {project.current_step === 6 && (
            <>
              <EffectWorkspace projectId={project.id} />
              <PreviewWorkspace
                projectId={project.id}
                pages={project.pages.map((page) => ({
                  page_id: page.id,
                  page_order: page.order,
                  title: page.title,
                  preview_path:
                    project.page_extractions?.find((item) => item.order === page.order)
                      ?.preview_path ?? null,
                }))}
                preflight={videoPreflightQuery.data ?? null}
                onPreflight={(settings) => {
                  if (settings) {
                    videoPreflightMutation.mutate(settings);
                    return;
                  }
                  void videoPreflightQuery.refetch();
                }}
                onRender={() => createRenderJobMutation.mutate()}
              />
              <PreflightWorkspace
                projectId={project.id}
                report={preflightQuery.data ?? null}
                onRun={() => preflightMutation.mutate()}
                onConfirm={(issueId, actor, note) =>
                  preflightConfirmMutation.mutate({ issueId, actor, note })
                }
                onExport={() => window.open(api.preflightReportUrl(project.id), '_blank')}
              />
            </>
          )}
          {project.current_step === 7 && <RenderJobPanel projectId={project.id} enabled />}
          {legacyRenderPanelEnabled && project!.current_step === 7 && (
            <section className="video-render-panel" aria-label="渲染与导出">
              <p className="success">完整预检已通过，可以开始渲染与导出。</p>
              <button
                className="primary"
                disabled={createRenderJobMutation.isPending || preflightQuery.data?.allowed !== true}
                onClick={() => createRenderJobMutation.mutate()}
              >
                {createRenderJobMutation.isPending ? '正在提交任务…' : '开始渲染与导出'}
              </button>
              {createRenderJobMutation.isError && (
                <p className="error">渲染失败。请检查预检结果和本地渲染环境后重试。</p>
              )}
              {createRenderJobMutation.data && (
                <p className="success">
                  渲染任务已提交：{createRenderJobMutation.data?.job.id}
                </p>
              )}
            </section>
          )}
        </section>
      </div>
    </main>
  );
}

type AudioRoute = 'local' | 'heygen' | null;

function inferAudioRoute(project: Project | undefined): AudioRoute {
  if (!project) return null;
  if (project.audio_import || project.pages.some((page) => page.audio?.source === 'local')) {
    return 'local';
  }
  if (project.pages.some((page) => page.audio?.source === 'heygen')) return 'heygen';
  return null;
}

function formatBytes(value: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  return `${size >= 10 || unit === 0 ? Math.round(size) : size.toFixed(1)} ${units[unit]}`;
}
