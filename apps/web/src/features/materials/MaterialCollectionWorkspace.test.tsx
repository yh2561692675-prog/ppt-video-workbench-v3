import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { MaterialCollectionRecord } from '../../api/client';
import { MaterialCollectionWorkspace } from './MaterialCollectionWorkspace';

const collection: MaterialCollectionRecord = {
  schema_version: '1.0',
  collection_id: 'collection-1',
  revision: 2,
  project_id: 'project-1',
  outline_mode: 'none',
  merge_policy: 'manual',
  documents: [{ document_id: 'doc-1', title: '讲义', role: 'reference', enabled: true }],
  presentations: [{ presentation_id: 'ppt-1', title: '课件', enabled: true, page_count: 2 }],
  sections: [
    { section_id: 'section-1', order: 0, title: '第一章', enabled: true, page_ids: ['page-1'] },
  ],
  page_sequence: [
    {
      material_page_id: 'page-1',
      source_ref: 'slides/1.png',
      order: 0,
      title: '页面一',
      section_id: 'section-1',
      enabled: true,
    },
  ],
  content_hash: 'a'.repeat(64),
};

describe('MaterialCollectionWorkspace', () => {
  it('shows sources, sections, pages and timeline sync action', () => {
    render(
      <MaterialCollectionWorkspace
        collection={collection}
        onCommand={vi.fn()}
        onSyncPreview={vi.fn()}
      />,
    );
    expect(screen.getAllByText('第一章')).not.toHaveLength(0);
    expect(screen.getByText('页面一')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '预览同步时间线' })).toBeInTheDocument();
  });
});
