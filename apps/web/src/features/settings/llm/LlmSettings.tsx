import { useMutation } from '@tanstack/react-query';
import { FormEvent, useState } from 'react';

import { api, LlmProfile } from '../../../api/client';

export function LlmSettings() {
  const [name, setName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [model, setModel] = useState('');
  const [saved, setSaved] = useState<LlmProfile | null>(null);
  const save = useMutation({
    mutationFn: api.createLlmProfile,
    onSuccess: (profile) => {
      setSaved(profile);
      setApiKey('');
    },
  });
  const test = useMutation({ mutationFn: api.testLlmProfile });

  function submit(event: FormEvent) {
    event.preventDefault();
    save.mutate({ name, base_url: baseUrl, api_key: apiKey, model });
  }

  return (
    <section className="llm-settings">
      <form className="settings-form" onSubmit={submit}>
        <label>
          配置名称
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label>
          Base URL
          <input
            type="url"
            value={baseUrl}
            onChange={(event) => setBaseUrl(event.target.value)}
            required
          />
        </label>
        <label>
          API Key
          <input
            type="password"
            value={apiKey}
            autoComplete="new-password"
            onChange={(event) => setApiKey(event.target.value)}
            required={!saved}
          />
        </label>
        <label>
          模型名称
          <input value={model} onChange={(event) => setModel(event.target.value)} required />
        </label>
        <button className="primary" type="submit" disabled={save.isPending}>
          安全保存配置
        </button>
      </form>
      {saved ? (
        <div className="settings-result">
          <strong>{saved.name}</strong>
          <span>密钥已由本机安全保护</span>
          <button
            className="secondary"
            type="button"
            disabled={test.isPending}
            onClick={() => test.mutate(saved.id)}
          >
            测试连接
          </button>
          {test.data?.ok ? <span className="success">连接成功</span> : null}
        </div>
      ) : null}
      {save.error ? <p className="error">{save.error.message}</p> : null}
      {test.error ? <p className="error">{test.error.message}</p> : null}
    </section>
  );
}
