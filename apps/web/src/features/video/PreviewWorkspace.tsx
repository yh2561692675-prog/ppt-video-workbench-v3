import { Player, PlayerRef } from '@remotion/player';
import type { ReactNode } from 'react';
import { useRef, useState } from 'react';

import type { RenderGraphV2Record, VideoPreflight } from '../../api/client';
import { ProjectVideo } from '../../../../../remotion/src/video/ProjectVideo';
import { RenderGraphPreview } from './RenderGraphPreview';
import { SubtitleStylePanel } from './SubtitleStylePanel';

export interface PreviewPage {
  page_id: string;
  page_order: number;
  title: string | null;
  preview_path: string | null;
}

interface PreviewWorkspaceProps {
  projectId: string;
  pages: PreviewPage[];
  preflight: VideoPreflight | null;
  onPreflight: (settings?: { reduced_motion: boolean }) => void;
  onRender: () => void;
  effectPlanMeta?: { revision: string | number; hash: string };
  effectControls?: ReactNode;
  renderGraph?: RenderGraphV2Record | null;
}

export function PreviewWorkspace({
  projectId,
  pages,
  preflight,
  onPreflight,
  onRender,
  effectPlanMeta,
  effectControls,
  renderGraph,
}: PreviewWorkspaceProps) {
  const [currentPage, setCurrentPage] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(preflight?.props?.reduced_motion ?? false);
  const page = pages[currentPage];
  const playerRef = useRef<PlayerRef>(null);
  const videoProps = preflight?.props ?? null;
  const playerProps = videoProps && {
    ...videoProps,
    pages: videoProps.pages.map((item) => ({
      ...item,
      image_path: projectAssetUrl(projectId, item.image_path),
      audio_path: projectAssetUrl(projectId, item.audio_path),
    })),
  };

  function togglePlayback() {
    if (playing) {
      playerRef.current?.pause();
      setPlaying(false);
      return;
    }
    playerRef.current?.play();
    setPlaying(true);
  }

  return (
    <section className="video-preview-workspace" aria-label="效果预览与完整预检">
      <div className="preview-heading">
        <div>
          <h3>效果预览与完整预检</h3>
          <p className="muted">项目 {projectId} 使用与最终渲染相同的页面 Props。</p>
        </div>
        <div className="preview-actions">
          <button
            className="secondary"
            onClick={() => onPreflight({ reduced_motion: reducedMotion })}
          >
            重新运行完整预检
          </button>
          <button className="primary" disabled={!preflight?.allowed} onClick={onRender}>
            开始渲染与导出
          </button>
        </div>
      </div>

      {effectPlanMeta && (
        <p className="preview-plan-meta" aria-label="特效计划版本">
          EffectPlan revision {effectPlanMeta.revision} · hash {effectPlanMeta.hash}
        </p>
      )}
      {effectControls}

      {renderGraph ? <RenderGraphPreview projectId={projectId} graph={renderGraph} /> : null}

      {preflight === null ? (
        <p className="muted">正在等待预检结果……</p>
      ) : preflight.allowed ? (
        <p className="success">完整预检已通过</p>
      ) : (
        <section className="video-preflight-blocked" aria-label="预检阻断原因">
          <h4>完整预检未通过</h4>
          <ul>
            {preflight.issues.map((issue, index) => (
              <li key={`${issue.code}-${issue.page_id ?? index}`}>
                <strong>{issue.page_id ? `页面 ${issue.page_id}：` : ''}</strong>
                {issue.message}
                <small>{issue.action}</small>
              </li>
            ))}
          </ul>
        </section>
      )}

      {page && (
        <div className="preview-canvas" data-page-id={page.page_id}>
          <div className="preview-toolbar">
            <label>
              跳转页面
              <select
                value={currentPage}
                onChange={(event) => setCurrentPage(Number(event.target.value))}
              >
                {pages.map((item, index) => (
                  <option key={item.page_id} value={index}>
                    第{item.page_order}页 {item.title ?? ''}
                  </option>
                ))}
              </select>
            </label>
            <button className="secondary" onClick={togglePlayback}>
              {playing ? '暂停预览' : '播放预览'}
            </button>
          </div>
          <div className="preview-frame">
            {videoProps && playerProps ? (
              <div data-testid="remotion-player">
                <Player
                  ref={playerRef}
                  component={ProjectVideo}
                  inputProps={{ props: { ...playerProps, reduced_motion: reducedMotion } }}
                  durationInFrames={Math.max(1, Math.round((videoProps.duration_ms * 30) / 1000))}
                  compositionWidth={videoProps.width}
                  compositionHeight={videoProps.height}
                  fps={videoProps.fps}
                  controls
                  acknowledgeRemotionLicense
                  style={{ width: '100%', aspectRatio: '16 / 9' }}
                />
              </div>
            ) : page.preview_path ? (
              <img src={page.preview_path} alt={page.title ?? `第${page.page_order}页`} />
            ) : (
              <p className="muted">本页尚无预览图。</p>
            )}
            <span className="preview-status">{playing ? '预览播放中' : '预览已暂停'}</span>
          </div>
        </div>
      )}

      <SubtitleStylePanel
        reducedMotion={reducedMotion}
        onReducedMotionChange={(value) => {
          setReducedMotion(value);
          onPreflight({ reduced_motion: value });
        }}
      />
    </section>
  );
}

function projectAssetUrl(projectId: string, relativePath: string): string {
  return `/api/projects/${projectId}/video/assets/${relativePath
    .split('/')
    .map(encodeURIComponent)
    .join('/')}`;
}
