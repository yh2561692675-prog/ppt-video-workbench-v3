import { useMemo, useState } from 'react';

import type { MaterialCollectionRecord } from '../../api/client';

interface MaterialCollectionWorkspaceProps {
  collection: MaterialCollectionRecord;
  onCommand: (command: { kind: string; payload: Record<string, unknown> }) => void;
  onSyncPreview: () => void;
}

export function MaterialCollectionWorkspace({
  collection,
  onCommand,
  onSyncPreview,
}: MaterialCollectionWorkspaceProps) {
  const [selectedSectionId, setSelectedSectionId] = useState<string | null>(
    collection.sections[0]?.section_id ?? null,
  );
  const selectedSection = collection.sections.find(
    (section) => section.section_id === selectedSectionId,
  );
  const pages = useMemo(
    () =>
      collection.page_sequence
        .filter((page) => page.section_id === selectedSectionId)
        .sort((a, b) => a.order - b.order),
    [collection.page_sequence, selectedSectionId],
  );

  return (
    <section className="material-collection-workspace" aria-label="材料组织">
      <div className="material-heading">
        <div>
          <h3>材料组织</h3>
          <p className="muted">
            Revision {collection.revision} · {collection.documents.length} 份文档 ·{' '}
            {collection.presentations.length} 套课件
          </p>
        </div>
        <button className="secondary" type="button" onClick={onSyncPreview}>
          预览同步时间线
        </button>
      </div>
      <div className="material-layout">
        <nav className="material-sections" aria-label="章节列表">
          {collection.sections.map((section) => (
            <button
              className={section.section_id === selectedSectionId ? 'selected' : ''}
              type="button"
              key={section.section_id}
              onClick={() => setSelectedSectionId(section.section_id)}
            >
              <strong>{section.title}</strong>
              <span>{section.page_ids.length} 页</span>
            </button>
          ))}
        </nav>
        <div className="material-pages">
          <div className="material-pages-heading">
            <strong>{selectedSection?.title ?? '未选择章节'}</strong>
            <button
              className="secondary"
              type="button"
              disabled={!selectedSection}
              onClick={() =>
                selectedSection &&
                onCommand({
                  kind: 'disable_page',
                  payload: { material_page_id: pages[0]?.material_page_id },
                })
              }
            >
              禁用首个页面
            </button>
          </div>
          {pages.length === 0 ? (
            <p className="muted">当前章节没有启用页面。</p>
          ) : (
            <ol>
              {pages.map((page) => (
                <li key={page.material_page_id} className={page.enabled ? '' : 'disabled'}>
                  <span>{page.order + 1}</span>
                  <div>
                    <strong>{page.title}</strong>
                    <small>{page.source_ref}</small>
                  </div>
                </li>
              ))}
            </ol>
          )}
        </div>
      </div>
    </section>
  );
}
