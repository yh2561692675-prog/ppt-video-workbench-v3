import { useEffect, useMemo, useRef, useState } from 'react';

import {
  api,
  ApiRequestError,
  HeyGenProfile,
  HeyGenVoice,
  NarrationPage,
} from '../../../api/client';

const PREVIEW_TEXT = '这是一段试听测试语音，用于确认当前声音效果。';
const MAX_BATCH_PASSES = 3;
const RETRYABLE_HEYGEN_CODES = new Set([
  'heygen_timeout',
  'heygen_network_error',
  'heygen_service_error',
  'heygen_rate_limited',
  'heygen_empty_audio',
]);

interface PageFailure {
  page: NarrationPage;
  cause: unknown;
}

interface Props {
  projectId: string;
  pages: NarrationPage[];
  localAudioActive: boolean;
  isLocalAudioActive: () => boolean;
  onStarted: () => boolean;
  onChanged: () => void;
}

export function HeyGenAudioPanel({
  projectId,
  pages,
  localAudioActive,
  isLocalAudioActive,
  onStarted,
  onChanged,
}: Props) {
  const orderedPages = useMemo(
    () => [...pages].sort((left, right) => left.order - right.order),
    [pages],
  );
  const unconfirmed = orderedPages.filter(
    (page) => !page.narration || page.narration.status !== 'completed',
  );
  const [profiles, setProfiles] = useState<HeyGenProfile[]>([]);
  const [voices, setVoices] = useState<HeyGenVoice[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(true);
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [profileLoadError, setProfileLoadError] = useState('');
  const [profileId, setProfileId] = useState('');
  const [voiceId, setVoiceId] = useState('');
  const [speed, setSpeed] = useState(1);
  const [completed, setCompleted] = useState(0);
  const [currentPage, setCurrentPage] = useState<NarrationPage | null>(null);
  const [busy, setBusy] = useState(false);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewAudioUrl, setPreviewAudioUrl] = useState('');
  const [error, setError] = useState('');
  const [complete, setComplete] = useState(false);
  const [batchPass, setBatchPass] = useState(1);
  const [profilesReloadKey, setProfilesReloadKey] = useState(0);
  const voiceRequestSequence = useRef(0);

  useEffect(() => {
    let active = true;
    setProfilesLoading(true);
    setProfileLoadError('');
    void api
      .listHeyGenProfiles()
      .then((available) => {
        if (active) setProfiles(available);
      })
      .catch((cause: unknown) => {
        if (active) {
          setProfiles([]);
          setProfileLoadError(cause instanceof Error ? cause.message : 'HeyGen 配置加载失败');
        }
      })
      .finally(() => {
        if (active) setProfilesLoading(false);
      });
    return () => {
      active = false;
    };
  }, [profilesReloadKey]);

  async function chooseProfile(nextProfileId: string) {
    const requestSequence = ++voiceRequestSequence.current;
    setProfileId(nextProfileId);
    setVoiceId('');
    setVoices([]);
    setPreviewAudioUrl('');
    setError('');
    if (!nextProfileId) {
      setVoicesLoading(false);
      return;
    }
    setVoicesLoading(true);
    try {
      const available = await api.listHeyGenVoices(nextProfileId);
      if (requestSequence === voiceRequestSequence.current) setVoices(available);
    } catch (cause) {
      if (requestSequence === voiceRequestSequence.current) {
        setError(formatRequestFailure(cause, '声音列表加载失败'));
      }
    } finally {
      if (requestSequence === voiceRequestSequence.current) setVoicesLoading(false);
    }
  }

  async function previewVoice() {
    if (!profileId || !voiceId || busy || previewBusy) return;
    setPreviewBusy(true);
    setPreviewAudioUrl('');
    setError('');
    try {
      const result = await api.previewHeyGenVoice(profileId, voiceId, PREVIEW_TEXT);
      setPreviewAudioUrl(result.audio_url);
    } catch (cause) {
      setError(formatRequestFailure(cause, '声音试听失败'));
    } finally {
      setPreviewBusy(false);
    }
  }

  async function synthesizeAll() {
    if (
      !profileId ||
      !voiceId ||
      localAudioActive ||
      isLocalAudioActive() ||
      unconfirmed.length > 0 ||
      busy ||
      previewBusy ||
      !onStarted()
    ) {
      return;
    }
    setBusy(true);
    setCompleted(0);
    setCurrentPage(null);
    setError('');
    setComplete(false);
    setBatchPass(1);
    const successfulPageIds = new Set<string>();
    let pendingPages = orderedPages;
    let failures: PageFailure[] = [];
    try {
      for (let pass = 1; pass <= MAX_BATCH_PASSES && pendingPages.length > 0; pass += 1) {
        setBatchPass(pass);
        failures = [];
        for (const page of pendingPages) {
          if (isLocalAudioActive()) {
            setCurrentPage(null);
            setError('检测到本地录音，已停止后续 HeyGen 页面配音生成。');
            return;
          }
          setCurrentPage(page);
          try {
            await api.synthesizeHeyGenAudio(projectId, page.id, {
              profile_id: profileId,
              revision_id: page.narration!.revision_id,
              voice_id: voiceId,
              speed,
              replace_existing: false,
            });
            successfulPageIds.add(page.id);
            setCompleted(successfulPageIds.size);
            onChanged();
          } catch (cause) {
            if (!isRetryableHeyGenFailure(cause)) {
              setCurrentPage(null);
              setError(formatFatalFailure(page, cause));
              return;
            }
            failures.push({ page, cause });
          }
          if (isLocalAudioActive()) {
            setCurrentPage(null);
            setError('检测到本地录音，已停止后续 HeyGen 页面配音生成。');
            return;
          }
        }
        pendingPages = failures.map((failure) => failure.page);
      }
      setCurrentPage(null);
      if (pendingPages.length > 0) {
        setError(formatExhaustedFailures(failures));
        return;
      }
      setComplete(true);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  const blocked =
    !profileId ||
    !voiceId ||
    profilesLoading ||
    voicesLoading ||
    localAudioActive ||
    isLocalAudioActive() ||
    unconfirmed.length > 0 ||
    busy ||
    previewBusy ||
    orderedPages.length === 0;
  const previewBlocked =
    !profileId || !voiceId || profilesLoading || voicesLoading || busy || previewBusy;
  return (
    <section
      className="heygen-audio-panel"
      aria-label="HeyGen 页面配音"
      aria-busy={profilesLoading || voicesLoading}
    >
      <div>
        <h3>HeyGen 页面配音</h3>
        <p className="muted">按页面顺序生成已确认旁白；不会覆盖已有页面配音。</p>
      </div>
      {profilesLoading && (
        <p className="muted" role="status">
          正在加载 HeyGen 配置...
        </p>
      )}
      {!profilesLoading && profiles.length === 0 && !profileLoadError && (
        <p className="muted">尚未保存 HeyGen 配置。请先在设置中安全保存 API Key。</p>
      )}
      {!profilesLoading && profileLoadError && (
        <div>
          <p className="error" role="alert">
            {profileLoadError}
          </p>
          <button
            type="button"
            className="secondary"
            onClick={() => setProfilesReloadKey((current) => current + 1)}
          >
            重试加载 HeyGen 配置
          </button>
        </div>
      )}
      {localAudioActive && <p className="error">已导入本地录音，不能同时使用 HeyGen 页面配音。</p>}
      {unconfirmed.length > 0 && <p className="error">仍有 {unconfirmed.length} 页旁白未确认</p>}
      <div className="heygen-audio-controls">
        <label>
          HeyGen 配置
          <select
            value={profileId}
            onChange={(event) => void chooseProfile(event.target.value)}
            disabled={busy || previewBusy || profilesLoading || profiles.length === 0}
          >
            <option value="">请选择配置</option>
            {profiles.map((profile) => (
              <option key={profile.id} value={profile.id}>
                {profile.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          声音
          <select
            value={voiceId}
            onChange={(event) => {
              setVoiceId(event.target.value);
              setPreviewAudioUrl('');
            }}
            disabled={busy || previewBusy || profilesLoading || voicesLoading || !profileId}
          >
            <option value="">请选择声音</option>
            {voices.map((voice) => (
              <option key={voice.voice_id} value={voice.voice_id}>
                {voice.name}（{voice.language}）
              </option>
            ))}
          </select>
        </label>
        {voicesLoading && (
          <p className="muted" role="status">
            正在加载可用声音...
          </p>
        )}
        <button
          type="button"
          className="secondary"
          disabled={previewBlocked}
          onClick={() => void previewVoice()}
        >
          {previewBusy ? '正在试听…' : '试听测试句'}
        </button>
        <label>
          语速 {speed.toFixed(1)}x
          <input
            aria-label="语速"
            type="range"
            min="0.5"
            max="2"
            step="0.1"
            value={speed}
            onChange={(event) => setSpeed(Number(event.target.value))}
            disabled={busy || previewBusy}
          />
        </label>
        <button className="primary" disabled={blocked} onClick={() => void synthesizeAll()}>
          {busy ? '正在生成页面配音…' : '使用 HeyGen 生成全部页面配音'}
        </button>
      </div>
      {previewAudioUrl && (
        <audio controls autoPlay preload="auto" src={previewAudioUrl} aria-label="试听音频">
          您的浏览器不支持音频播放。
        </audio>
      )}
      {busy && currentPage && (
        <p role="status">
          第 {batchPass} / {MAX_BATCH_PASSES} 轮：正在生成第 {currentPage.order} 页“
          {currentPage.title ?? '未命名页'}”
        </p>
      )}
      {completed > 0 && (
        <p className="success">
          已完成 {completed} / {orderedPages.length} 页
        </p>
      )}
      {complete && <p className="success">全部 {orderedPages.length} 页 HeyGen 配音已生成。</p>}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}

function isRetryableHeyGenFailure(cause: unknown): boolean {
  if (!(cause instanceof ApiRequestError)) return true;
  return RETRYABLE_HEYGEN_CODES.has(cause.code);
}

function formatFatalFailure(page: NarrationPage, cause: unknown): string {
  const message = cause instanceof Error ? cause.message : '请求失败';
  const action = cause instanceof ApiRequestError ? `；${cause.action}` : '';
  return `第 ${page.order} 页“${page.title ?? '未命名页'}”无法继续：${message}${action}`;
}

function formatRequestFailure(cause: unknown, fallback: string): string {
  if (cause instanceof ApiRequestError) {
    return cause.action ? `${cause.message}；${cause.action}` : cause.message;
  }
  return cause instanceof Error ? cause.message : fallback;
}

function formatExhaustedFailures(failures: PageFailure[]): string {
  const details = failures
    .map(({ page, cause }) => {
      const message = cause instanceof Error ? cause.message : '请求失败';
      return `第 ${page.order} 页“${page.title ?? '未命名页'}”：${message}`;
    })
    .join('；');
  return `自动补跑 ${MAX_BATCH_PASSES} 轮后仍有 ${failures.length} 页未完成：${details}`;
}
