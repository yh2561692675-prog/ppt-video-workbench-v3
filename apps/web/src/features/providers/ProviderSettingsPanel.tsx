import { useQuery } from '@tanstack/react-query';

import { api } from '../../api/client';

export function ProviderSettingsPanel() {
  const providers = useQuery({ queryKey: ['p2-providers'], queryFn: api.p2Providers });
  const credentials = useQuery({ queryKey: ['p2-credentials'], queryFn: api.p2Credentials });

  if (providers.isLoading) return <section className="panel">正在读取 Provider 能力…</section>;
  if (providers.isError) {
    return (
      <section className="panel" role="alert">
        <h2>Provider 平台未启用</h2>
        <p className="muted">请启用 PROVIDER_PLATFORM_ENABLED 后重新打开本页。</p>
      </section>
    );
  }

  const providerList = providers.data ?? [];

  return (
    <section className="p2-settings-grid">
      <article className="panel">
        <div className="p2-section-heading">
          <div>
            <h2>Provider 能力</h2>
            <p className="muted">只显示已审核的内置适配边界，不执行动态第三方代码。</p>
          </div>
          <span className="status-pill success">{providerList.length} 个已注册</span>
        </div>
        <div className="p2-card-list">
          {providerList.map((provider) => (
            <article className="p2-card" key={provider.provider_id}>
              <div>
                <strong>{provider.display_name}</strong>
                <span className="muted">
                  {provider.kind} · {provider.execution_mode}
                </span>
              </div>
              <div className="p2-chip-list">
                {provider.capabilities.map((capability) => (
                  <span className="p2-chip" key={capability.capability_id}>
                    {capability.capability_id}
                  </span>
                ))}
              </div>
            </article>
          ))}
        </div>
      </article>
      <article className="panel">
        <div className="p2-section-heading">
          <div>
            <h2>凭证状态</h2>
            <p className="muted">页面只读取元数据，永远不回显密钥。</p>
          </div>
        </div>
        {credentials.isLoading ? <p className="muted">正在读取…</p> : null}
        {credentials.isError ? <p className="error">系统凭证库不可用，已安全阻断。</p> : null}
        {credentials.data?.length ? (
          <div className="p2-card-list">
            {credentials.data.map((credential) => (
              <div className="p2-card" key={credential.credential_ref}>
                <strong>{credential.credential_ref}</strong>
                <span className="muted">
                  {credential.provider_id} · {credential.status} · {credential.scope}
                </span>
              </div>
            ))}
          </div>
        ) : credentials.isSuccess ? (
          <p className="muted">暂无凭证元数据。</p>
        ) : null}
      </article>
    </section>
  );
}
