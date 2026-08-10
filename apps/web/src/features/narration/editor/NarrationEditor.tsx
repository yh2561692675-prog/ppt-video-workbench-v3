import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';

import { api, NarrationPage, NarrationRevision } from '../../../api/client';

interface Props {
  projectId: string;
  page: NarrationPage;
  pageText: string;
  outlineText: string;
}

export function NarrationEditor({ projectId, page, pageText, outlineText }: Props) {
  const queryClient = useQueryClient();
  const queryKey = ['narration-revisions', projectId, page.id];
  const history = useQuery({
    queryKey,
    queryFn: () => api.listNarrationRevisions(projectId, page.id),
  });
  const profiles = useQuery({ queryKey: ['llm-profiles'], queryFn: api.listLlmProfiles });
  const initial = page.narration;
  const [text, setText] = useState(initial?.text ?? '');
  const [currentRevisionId, setCurrentRevisionId] = useState<string | null>(
    initial?.revision_id ?? null,
  );
  const [currentVersion, setCurrentVersion] = useState(initial?.version ?? 0);
  const [sourceRefs, setSourceRefs] = useState(initial?.source_refs ?? []);
  const [profileId, setProfileId] = useState('');

  useEffect(() => {
    const latest = history.data?.at(-1);
    if (!latest || currentRevisionId) return;
    setText(latest.text);
    setCurrentRevisionId(latest.id);
    setCurrentVersion(latest.version);
  }, [currentRevisionId, history.data]);

  const characterCount = useMemo(() => text.replaceAll(/\s/g, '').length, [text]);
  const duration = Math.max(characterCount / 4, 0);
  const selectedProfileId = profileId || profiles.data?.[0]?.id || '';

  function accept(revision: NarrationRevision) {
    setText(revision.text);
    setCurrentRevisionId(revision.id);
    setCurrentVersion(revision.version);
    setSourceRefs(revision.source_refs);
    queryClient.setQueryData<NarrationRevision[]>(queryKey, (existing = []) => [
      ...existing,
      revision,
    ]);
    void queryClient.invalidateQueries({ queryKey: ['project', projectId] });
  }

  const save = useMutation({
    mutationFn: () =>
      api.saveNarrationRevision(projectId, page.id, {
        text,
        author: '规划师',
        expected_revision_id: currentRevisionId,
        source_refs: sourceRefs,
      }),
    onSuccess: accept,
  });
  const restore = useMutation({
    mutationFn: (revisionId: string) => {
      if (!currentRevisionId) throw new Error('当前版本尚未保存');
      return api.restoreNarrationRevision(projectId, page.id, revisionId, currentRevisionId);
    },
    onSuccess: accept,
  });
  const generate = useMutation({
    mutationFn: () => {
      if (!selectedProfileId) throw new Error('请先在模型设置中保存可用配置');
      return api.generateNarration(projectId, page.id, selectedProfileId);
    },
    onSuccess: accept,
  });

  return (
    <div className="narration-editor">
      <div className="narration-source">
        <h3>{page.title ?? `第 ${page.order} 页`}</h3>
        <div className="source-columns">
          <section>
            <strong>课件原文</strong>
            <p>{pageText || '本页没有可提取文字'}</p>
          </section>
          <section>
            <strong>匹配大纲</strong>
            <p>{outlineText || '本页没有匹配大纲'}</p>
          </section>
        </div>
      </div>
      <div className="editor-panel">
        <div className="editor-meta">
          <span>版本 {currentVersion}</span>
          <span>字数 {characterCount}</span>
          <span>语速 240 字/分钟</span>
          <span>预计 {duration.toFixed(1)} 秒</span>
        </div>
        <div className="generation-controls">
          <label>
            模型配置
            <select
              value={selectedProfileId}
              onChange={(event) => setProfileId(event.target.value)}
            >
              {!profiles.data?.length ? <option value="">尚未配置模型</option> : null}
              {profiles.data?.map((profile) => (
                <option key={profile.id} value={profile.id}>
                  {profile.name} · {profile.model}
                </option>
              ))}
            </select>
          </label>
          <button
            className="secondary"
            onClick={() => generate.mutate()}
            disabled={!selectedProfileId || generate.isPending}
          >
            {generate.isPending ? '生成中……' : '生成 AI 草稿'}
          </button>
        </div>
        <label>
          旁白正文
          <textarea value={text} rows={10} onChange={(event) => setText(event.target.value)} />
        </label>
        <button className="primary" onClick={() => save.mutate()} disabled={!text.trim()}>
          保存新版本
        </button>
        {save.error ? <p className="error">{save.error.message}</p> : null}
        {generate.error ? <p className="error">{generate.error.message}</p> : null}
      </div>
      <aside className="revision-history">
        <h3>历史版本</h3>
        {history.data?.map((revision) => (
          <div className="revision-card" key={revision.id}>
            <span>
              v{revision.version} · {revision.author}
            </span>
            <p>{revision.text}</p>
            {revision.id !== currentRevisionId ? (
              <button className="secondary" onClick={() => restore.mutate(revision.id)}>
                恢复版本 {revision.version}
              </button>
            ) : null}
          </div>
        ))}
      </aside>
    </div>
  );
}
