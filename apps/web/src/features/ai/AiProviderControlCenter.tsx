import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api } from '../../api/client';

const MODEL_STATUS: Record<string, string> = {
  active: '已激活',
  ready: '已就绪',
  degraded: '降级',
  failed: '失败',
  incompatible: '不兼容',
  not_installed: '未安装',
};

const ASSIST_KIND: Record<string, string> = {
  polish: '旁白润色',
  segment: '智能断句',
  translate: '字幕翻译',
};

export function AiProviderControlCenter() {
  const [platformEnabled, setPlatformEnabled] = useState(false);
  const queryClient = useQueryClient();
  const models = useQuery({ queryKey: ['ai-models'], queryFn: () => api.listAiModels() });
  const voices = useQuery({ queryKey: ['ai-voices'], queryFn: api.listAiVoices });
  const candidates = useQuery({
    queryKey: ['ai-content-assist-candidates'],
    queryFn: api.listContentAssistCandidates,
  });
  const providers = useQuery({
    queryKey: ['ai-providers'],
    queryFn: api.p2Providers,
    enabled: platformEnabled,
  });
  const acceptCandidate = useMutation({
    mutationFn: api.acceptContentAssistCandidate,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ai-content-assist-candidates'] }),
  });
  const revokeVoice = useMutation({
    mutationFn: api.revokeAiVoice,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['ai-voices'] }),
  });

  return (
    <div className="ai-control-center">
      <section className="panel ai-policy-panel">
        <div className="p2-section-heading">
          <div>
            <h2>本地优先策略</h2>
            <p className="muted">
              本地音频链不依赖 Provider。远端服务、上传和费用操作都必须单独启用。
            </p>
          </div>
          <span className={`status-pill ${platformEnabled ? 'warning' : 'success'}`}>
            {platformEnabled ? '已显式启用控制面' : '默认关闭'}
          </span>
        </div>
        <label className="ai-toggle">
          <input
            type="checkbox"
            checked={platformEnabled}
            onChange={(event) => setPlatformEnabled(event.target.checked)}
          />
          <span>启用 AI / Provider 控制面（不会自动启用远端 Provider）</span>
        </label>
        <div className="ai-local-chain" role="status">
          <strong>本地生产链：可独立运行</strong>
          <span className="muted">音频导入 · 本地 ASR/TTS · 字幕 · 预览 · 渲染</span>
        </div>
      </section>

      <section className="ai-card-grid">
        <article className="panel">
          <div className="p2-section-heading">
            <div>
              <h2>本地模型中心</h2>
              <p className="muted">只管理本机模型，不在页面打开时自动下载。</p>
            </div>
            <span className="status-pill success">本地</span>
          </div>
          {models.isLoading ? <p className="muted">正在读取模型库存…</p> : null}
          {models.isError ? (
            <p className="error">模型中心暂时不可用，本地音频导入仍可继续。</p>
          ) : null}
          {models.data?.length ? (
            <div className="p2-card-list">
              {models.data.map((model) => (
                <div
                  className="p2-card"
                  key={`${model.descriptor.model_id}-${model.descriptor.revision}`}
                >
                  <strong>{model.descriptor.display_name}</strong>
                  <span className="muted">
                    {model.descriptor.kind} · {model.descriptor.engine} ·{' '}
                    {MODEL_STATUS[model.install.status] ?? model.install.status}
                  </span>
                  <span className="muted">
                    {model.last_probe
                      ? `probe: ${model.last_probe.status} / ${model.last_probe.device}`
                      : '尚未 probe'}
                  </span>
                </div>
              ))}
            </div>
          ) : models.isSuccess ? (
            <p className="muted">暂无已安装模型。可继续使用导入音频和已有 transcript。</p>
          ) : null}
        </article>

        <article className="panel">
          <div className="p2-section-heading">
            <div>
              <h2>声音身份</h2>
              <p className="muted">默认 local-only；撤销后阻断新任务。</p>
            </div>
            <span className="status-pill success">不上传</span>
          </div>
          {voices.isLoading ? <p className="muted">正在读取声音身份…</p> : null}
          {voices.isError ? <p className="error">声音仓库不可用，已安全阻断。</p> : null}
          {voices.data?.length ? (
            <div className="p2-card-list">
              {voices.data.map((voice) => (
                <div className="p2-card" key={voice.voice_id}>
                  <strong>{voice.display_name}</strong>
                  <span className="muted">
                    {voice.kind} · {voice.local_only ? 'local-only' : 'remote-capable'} ·{' '}
                    {voice.status}
                  </span>
                  {voice.status === 'active' ? (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => revokeVoice.mutate(voice.voice_id)}
                      disabled={revokeVoice.isPending}
                    >
                      撤销身份
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : voices.isSuccess ? (
            <p className="muted">暂无声音身份；无授权样本时不会启动克隆训练。</p>
          ) : null}
        </article>
      </section>

      <section className="ai-card-grid">
        <article className="panel">
          <div className="p2-section-heading">
            <div>
              <h2>Provider 治理与远端批次</h2>
              <p className="muted">预算、限流、未知计费对账和批次恢复必须经过 Broker。</p>
            </div>
            <span className={`status-pill ${platformEnabled ? 'warning' : 'success'}`}>
              {platformEnabled ? '等待显式 Provider' : '已关闭'}
            </span>
          </div>
          {!platformEnabled ? (
            <p className="muted">控制面关闭时不读取 Provider，也不会发起远端请求。</p>
          ) : providers.isLoading ? (
            <p className="muted">正在读取 Provider 能力…</p>
          ) : providers.isError ? (
            <p className="error">Provider 平台不可用，已失败关闭。</p>
          ) : (
            <div className="p2-card-list">
              {(providers.data ?? []).map((provider) => (
                <div className="p2-card" key={provider.provider_id}>
                  <strong>{provider.display_name}</strong>
                  <span className="muted">
                    {provider.kind} · {provider.enabled ? '已注册' : '已禁用'} · {provider.trust}
                  </span>
                </div>
              ))}
              {!providers.data?.length ? <p className="muted">暂无已注册 Provider。</p> : null}
            </div>
          )}
        </article>

        <article className="panel">
          <div className="p2-section-heading">
            <div>
              <h2>内容辅助候选</h2>
              <p className="muted">旁白润色、智能断句和字幕翻译只生成候选，不自动覆盖活动版本。</p>
            </div>
            <span className="status-pill success">候选审阅</span>
          </div>
          {candidates.isLoading ? <p className="muted">正在读取候选…</p> : null}
          {candidates.isError ? <p className="error">候选仓库不可用。</p> : null}
          {candidates.data?.length ? (
            <div className="p2-card-list">
              {candidates.data.map((candidate) => (
                <div className="p2-card" key={candidate.candidate_id}>
                  <strong>{ASSIST_KIND[candidate.kind] ?? candidate.kind}</strong>
                  <span className="muted">
                    {candidate.status} · {candidate.provider_id ?? '本地规则'}
                  </span>
                  <span>{candidate.candidate_text}</span>
                  {candidate.status === 'candidate' ? (
                    <button
                      type="button"
                      className="secondary-button"
                      onClick={() => acceptCandidate.mutate(candidate.candidate_id)}
                      disabled={acceptCandidate.isPending}
                    >
                      接受候选
                    </button>
                  ) : null}
                </div>
              ))}
            </div>
          ) : candidates.isSuccess ? (
            <p className="muted">暂无候选。翻译无 Provider 时会保持 needs_provider。</p>
          ) : null}
        </article>
      </section>
    </div>
  );
}
