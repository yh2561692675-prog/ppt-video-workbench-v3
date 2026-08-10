import { ChangeEvent, useState } from 'react';

import { api, AudioImportRecord } from '../../../api/client';

interface Props {
  projectId: string;
  initialAudio: AudioImportRecord | null;
  disabled?: boolean;
  disabledReason?: string;
  onImported?: () => void;
}

export function AudioImport({
  projectId,
  initialAudio,
  disabled = false,
  disabledReason,
  onImported,
}: Props) {
  const [audio, setAudio] = useState(initialAudio);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');

  function choose(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setMessage('');
  }

  async function upload() {
    if (!file) return;
    setBusy(true);
    try {
      setAudio(await api.importAudio(projectId, file));
      onImported?.();
      setMessage('录音已导入并规范化');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '录音导入失败');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="audio-import">
      <div className="drop-zone">
        <label htmlFor="local-audio">选择本地录音</label>
        <input
          id="local-audio"
          type="file"
          accept=".mp3,.wav"
          disabled={disabled}
          onChange={choose}
        />
        <button
          className="primary"
          disabled={disabled || !file || busy}
          onClick={() => void upload()}
        >
          {busy ? '规范化中…' : '导入并规范化'}
        </button>
      </div>
      {disabled && disabledReason && <p className="error">{disabledReason}</p>}
      {message && <p role="status">{message}</p>}
      {audio && (
        <div className="audio-summary">
          <strong>本地录音</strong>
          <span>
            {audio.sample_rate / 1000} kHz · {audio.channels === 1 ? '单声道' : '立体声'} ·{' '}
            {(audio.duration_ms / 1000).toFixed(1)} 秒
          </span>
          {audio.needs_confirmation && <p>检测到异常静音，请试听并确认。</p>}
        </div>
      )}
    </section>
  );
}
