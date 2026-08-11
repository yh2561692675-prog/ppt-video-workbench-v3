import { useMemo, useState } from 'react';

import type { AssetRecord } from '../../api/client';

interface AssetLibraryProps {
  assets: AssetRecord[];
  onSelect: (asset: AssetRecord) => void;
  onCreateOverlay?: (asset: AssetRecord) => void;
}

export function AssetLibrary({ assets, onSelect, onCreateOverlay }: AssetLibraryProps) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('all');
  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return assets.filter((asset) => {
      const matchesKind = kind === 'all' || asset.kind === kind;
      const matchesQuery =
        !normalized ||
        asset.original_name.toLowerCase().includes(normalized) ||
        asset.tags.some((tag) => tag.toLowerCase().includes(normalized));
      return matchesKind && matchesQuery;
    });
  }, [assets, kind, query]);

  return (
    <section className="asset-library" aria-label="素材库">
      <div className="asset-library-heading">
        <div>
          <h3>素材库</h3>
          <p className="muted">按内容 hash、授权状态和标签复用项目素材。</p>
        </div>
        <span className="muted">{filtered.length} 项</span>
      </div>
      <div className="asset-library-filters">
        <input
          aria-label="搜索素材"
          placeholder="搜索名称或标签"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
        <select
          aria-label="素材类型"
          value={kind}
          onChange={(event) => setKind(event.target.value)}
        >
          <option value="all">全部类型</option>
          <option value="image">图片</option>
          <option value="video">视频</option>
          <option value="audio">音频</option>
          <option value="logo">Logo</option>
          <option value="sticker">贴纸</option>
        </select>
      </div>
      {filtered.length === 0 ? (
        <p className="muted">暂无符合条件的素材。</p>
      ) : (
        <ul className="asset-library-grid">
          {filtered.map((asset) => (
            <li className="asset-card" key={asset.asset_id}>
              <button type="button" onClick={() => onSelect(asset)}>
                <strong>{asset.original_name}</strong>
                <span>
                  {asset.kind} · r{asset.revision}
                </span>
                <span className={`asset-license asset-license-${asset.license.status}`}>
                  授权：{asset.license.status}
                </span>
              </button>
              {onCreateOverlay && (asset.kind === 'image' || asset.kind === 'video') ? (
                <button type="button" className="secondary" onClick={() => onCreateOverlay(asset)}>
                  放入时间线
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
