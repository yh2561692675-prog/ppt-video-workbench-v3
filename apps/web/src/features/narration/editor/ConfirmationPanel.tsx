import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { api, NarrationPage } from '../../../api/client';

interface Props {
  projectId: string;
  pages: NarrationPage[];
  conflictsByPage: Record<string, string[]>;
}

export function ConfirmationPanel({ projectId, pages, conflictsByPage }: Props) {
  const queryClient = useQueryClient();
  const [showSummary, setShowSummary] = useState(false);
  const [resolutions, setResolutions] = useState<Record<string, string>>({});
  const [confirmedCount, setConfirmedCount] = useState(0);
  const gate = useQuery({
    queryKey: ['narration-gate', projectId],
    queryFn: () => api.narrationGate(projectId),
  });
  const pending = pages.filter((page) => page.narration && page.narration.status !== 'completed');
  const unresolved = pending.some(
    (page) => (conflictsByPage[page.id]?.length ?? 0) > 0 && !resolutions[page.id]?.trim(),
  );
  const confirm = useMutation({
    mutationFn: () =>
      api.confirmNarrationsBatch(
        projectId,
        pending.flatMap((page) =>
          page.narration
            ? [
                {
                  page_id: page.id,
                  revision_id: page.narration.revision_id,
                  conflict_resolution: resolutions[page.id]?.trim() || undefined,
                },
              ]
            : [],
        ),
      ),
    onSuccess: (items) => {
      setConfirmedCount(items.length);
      void queryClient.invalidateQueries({ queryKey: ['project', projectId] });
      void queryClient.invalidateQueries({ queryKey: ['narration-gate', projectId] });
    },
  });

  return (
    <section className="confirmation-panel">
      <div className="confirmation-header">
        <div>
          <h3>旁白确认门禁</h3>
          <p className="muted">确认只绑定当前版本；后续编辑会自动重新锁定音频阶段。</p>
        </div>
        <button className="secondary" onClick={() => setShowSummary((value) => !value)}>
          查看批量确认摘要
        </button>
      </div>
      {gate.data?.reasons.map((reason) => {
        const page = pages.find((item) => item.id === reason.page_id);
        return (
          <a key={`${reason.page_id}-${reason.code}`} href={`#narration-page-${reason.page_id}`}>
            跳转到{page?.title ?? `第${page?.order ?? '?'}页`}
          </a>
        );
      })}
      {showSummary ? (
        <div className="confirmation-summary">
          <strong>{pending.length} 页待确认</strong>
          {pending.map((page) => (
            <div className="confirmation-item" key={page.id}>
              <span>
                {page.title ?? `第 ${page.order} 页`} · 当前 v{page.narration?.version}
              </span>
              {conflictsByPage[page.id]?.map((conflict) => (
                <p key={conflict}>{conflict}</p>
              ))}
              {(conflictsByPage[page.id]?.length ?? 0) > 0 ? (
                <label>
                  {page.title ?? `第${page.order}页`}冲突处理说明
                  <input
                    value={resolutions[page.id] ?? ''}
                    onChange={(event) =>
                      setResolutions((current) => ({
                        ...current,
                        [page.id]: event.target.value,
                      }))
                    }
                  />
                </label>
              ) : null}
            </div>
          ))}
          <button
            className="primary"
            disabled={!pending.length || unresolved || confirm.isPending}
            onClick={() => confirm.mutate()}
          >
            确认全部当前版本
          </button>
          {confirmedCount ? <span className="success">已确认 {confirmedCount} 页</span> : null}
          {confirm.error ? <p className="error">{confirm.error.message}</p> : null}
        </div>
      ) : null}
    </section>
  );
}
