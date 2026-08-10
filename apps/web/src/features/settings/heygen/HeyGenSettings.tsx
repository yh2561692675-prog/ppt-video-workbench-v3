import { FormEvent, useEffect, useState } from 'react';

import { api, HeyGenProfile, HeyGenVoice } from '../../../api/client';

export function HeyGenSettings() {
  const [name, setName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [profile, setProfile] = useState<HeyGenProfile | null>(null);
  const [profiles, setProfiles] = useState<HeyGenProfile[]>([]);
  const [voices, setVoices] = useState<HeyGenVoice[]>([]);
  const [voiceId, setVoiceId] = useState('');
  const [previewUrl, setPreviewUrl] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void api
      .listHeyGenProfiles()
      .then((available) => {
        setProfiles(available);
        const selected = available[0] ?? null;
        setProfile(selected);
        setName(selected?.name ?? '');
      })
      .catch((error: unknown) => {
        setMessage(error instanceof Error ? error.message : '无法读取 HeyGen 配置');
      });
  }, []);

  function selectProfile(profileId: string) {
    const selected = profiles.find((candidate) => candidate.id === profileId) ?? null;
    setProfile(selected);
    setName(selected?.name ?? '');
    setApiKey('');
    setVoices([]);
    setVoiceId('');
    setPreviewUrl('');
    setMessage('');
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      const payload = {
        name,
        base_url: 'https://api.heygen.com',
        api_key: apiKey,
      };
      const saved = profile
        ? await api.updateHeyGenProfile(profile.id, payload)
        : await api.createHeyGenProfile(payload);
      setProfile(saved);
      setProfiles((current) => {
        const remaining = current.filter((candidate) => candidate.id !== saved.id);
        return [...remaining, saved];
      });
      setApiKey('');
      const available = await api.listHeyGenVoices(saved.id);
      setVoices(available);
      setVoiceId(available[0]?.voice_id ?? '');
      setMessage('连接成功，密钥已由本机安全保护');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '配置保存失败');
    } finally {
      setBusy(false);
    }
  }

  async function preview() {
    if (!profile || !voiceId) return;
    setBusy(true);
    try {
      const result = await api.previewHeyGenVoice(profile.id, voiceId, '这是一段声音测试。');
      setPreviewUrl(result.audio_url);
      setMessage('试听已生成');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '试听生成失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="llm-settings">
      <p className="muted">
        填写 HeyGen API Key 后，系统会先验证连接并加载可用音色；密钥只保存在本机。
      </p>
      <form className="settings-form" onSubmit={(event) => void submit(event)}>
        {profiles.length > 0 && (
          <label>
            当前 HeyGen 配置
            <select
              value={profile?.id ?? ''}
              onChange={(event) => selectProfile(event.target.value)}
            >
              {profiles.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <label>
          配置名称
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          HeyGen API Key
          <input
            type="password"
            value={apiKey}
            autoComplete="new-password"
            onChange={(event) => setApiKey(event.target.value)}
            required={!profile}
          />
        </label>
        <button className="primary" type="submit" disabled={busy}>
          {profile ? '更新 HeyGen 配置' : '安全保存 HeyGen 配置'}
        </button>
      </form>
      {voices.length > 0 && (
        <div className="settings-form">
          <label>
            本人声音
            <select value={voiceId} onChange={(event) => setVoiceId(event.target.value)}>
              {voices.map((voice) => (
                <option key={voice.voice_id} value={voice.voice_id}>
                  {voice.name}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            type="button"
            disabled={busy}
            onClick={() => void preview()}
          >
            试听测试句
          </button>
          {previewUrl && <audio controls src={previewUrl} />}
        </div>
      )}
      {message && <p role="status">{message}</p>}
    </section>
  );
}
