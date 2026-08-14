import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../api/client';

export function EffectWorkspace({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const workspace = useQuery({
    queryKey: ['effects', projectId],
    queryFn: () => api.effectWorkspace(projectId),
  });
  const release = useQuery({
    queryKey: ['release-status'],
    queryFn: () => api.releaseStatus(),
    staleTime: Infinity,
  });
  const generate = useMutation({
    mutationFn: () => api.generateEffects(projectId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['effects', projectId] }),
  });

  if (workspace.isLoading) return <p className="muted">特效计划加载中……</p>;
  if (workspace.isError || !workspace.data) return <p className="error">特效计划暂时无法加载。</p>;
  const pages = workspace.data.pages;
  const missing = pages.filter((page) => page.record === null).length;
  return (
    <section className="effect-workspace" aria-label="特效计划工作台">
      <div className="effect-policy-banner" role="status">
        {release.isLoading ? (
          <span className="muted">正在读取版本特效策略…</span>
        ) : release.isError || !release.data ? (
          <span className="error">版本特效策略未能读取，请先校验候选版本。</span>
        ) : (
          <span>
            候选 {release.data.candidate_id ?? '未绑定'} · 旧项目 V1 · 新项目{' '}
            {release.data.feature_policy.new_project_default.toUpperCase()} · 特效 V2{' '}
            {release.data.feature_policy.effects_v2.render ? '已启用' : '未启用'} ·{' '}
            {release.data.feature_policy.allow_fallback ? '允许降级' : '禁止降级'}
          </span>
        )}
      </div>
      <div className="preview-heading">
        <div>
          <h3>特效引擎 V2</h3>
          <p className="muted">
            目录 {workspace.data.catalog_version} · {pages.length} 页
          </p>
        </div>
        <button
          className="secondary"
          disabled={generate.isPending}
          onClick={() => generate.mutate()}
        >
          {generate.isPending
            ? '正在生成……'
            : missing
              ? `生成缺失计划（${missing}）`
              : '重新生成未锁定页'}
        </button>
      </div>
      <ul className="effect-page-status">
        {pages.map((page) => (
          <li key={page.page_id}>
            <span>
              第{page.page_order}页 {page.title ?? ''}
            </span>
            <span className="status-pill">
              {page.record ? `${page.record.status} · r${page.record.revision}` : '未生成'}
            </span>
          </li>
        ))}
      </ul>
      {generate.isError && <p className="error">特效计划生成失败，请查看服务端校验信息。</p>}
    </section>
  );
}
