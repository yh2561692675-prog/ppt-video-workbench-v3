import { useQuery } from '@tanstack/react-query';

import { api, P2CapabilityStatus } from '../../../api/client';

const STATUS_LABEL: Record<P2CapabilityStatus, string> = {
  supported: '支持',
  missing: '缺失',
  misconfigured: '未配置',
  temporarily_unavailable: '暂时不可用',
  unsupported: '不支持',
};

export function PlatformSettingsPanel() {
  const diagnostics = useQuery({ queryKey: ['p2-diagnostics'], queryFn: api.p2Diagnostics });

  if (diagnostics.isLoading) return <section className="panel">正在读取平台能力…</section>;
  const data = diagnostics.data;
  if (diagnostics.isError || !data?.platform) {
    return (
      <section className="panel" role="alert">
        <h2>平台服务未启用</h2>
        <p className="muted">请启用 PLATFORM_SERVICES_ENABLED 后重新打开本页。</p>
      </section>
    );
  }

  const platform = data.platform;
  return (
    <section className="panel">
      <div className="p2-section-heading">
        <div>
          <h2>
            {platform.info.platform} · {platform.info.architecture}
          </h2>
          <p className="muted">
            runtime {platform.info.runtime_version} · app {platform.info.app_version}
          </p>
        </div>
        <code>{platform.fingerprint.slice(0, 20)}…</code>
      </div>
      <div className="p2-card-list">
        {platform.capability_states.map((capability) => (
          <article className="p2-card" key={capability.capability_id}>
            <strong>{capability.capability_id}</strong>
            <span className={`status-pill ${capability.status === 'supported' ? 'success' : 'warning'}`}>
              {STATUS_LABEL[capability.status]}
            </span>
            {capability.detail ? <span className="muted">{capability.detail}</span> : null}
          </article>
        ))}
      </div>
    </section>
  );
}
