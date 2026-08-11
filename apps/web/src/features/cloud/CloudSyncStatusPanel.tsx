import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';

export function CloudSyncStatusPanel() {
  const diagnostics = useQuery({ queryKey: ['p2-diagnostics'], queryFn: api.p2Diagnostics });

  if (diagnostics.isLoading) return <section className="panel">正在读取同步状态…</section>;
  if (diagnostics.isError) {
    return (
      <section className="panel" role="alert">
        <h2>云端同步未启用</h2>
        <p className="muted">本地优先项目仍可继续工作；启用 CLOUD_SYNC_ENABLED 后再连接云端。</p>
      </section>
    );
  }

  const sync = diagnostics.data?.sync ?? null;
  return (
    <section className="panel">
      <h2>云端同步</h2>
      <p className="muted">同步数据库只保存 outbox/inbox，不写入项目正文。</p>
      {sync ? (
        <dl className="p2-definition-list">
          {Object.entries(sync).map(([key, value]) => (
            <div key={key}>
              <dt>{key}</dt>
              <dd>{String(value)}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="muted">当前为本地模式，未创建同步数据库。</p>
      )}
    </section>
  );
}
