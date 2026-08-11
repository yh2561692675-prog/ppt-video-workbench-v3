import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { api } from '../../api/client';

export function EffectWorkspace({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const workspace = useQuery({
    queryKey: ['effects', projectId],
    queryFn: () => api.effectWorkspace(projectId),
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
