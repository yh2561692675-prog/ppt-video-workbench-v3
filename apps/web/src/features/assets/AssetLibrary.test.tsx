import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { AssetRecord } from '../../api/client';
import { AssetLibrary } from './AssetLibrary';

const assets: AssetRecord[] = [
  {
    asset_id: 'asset-image',
    revision: 1,
    project_id: 'project-1',
    kind: 'image',
    content_hash: 'a'.repeat(64),
    relative_object_path: 'workspace-data/assets/a.png',
    original_name: 'Logo.png',
    mime_type: 'image/png',
    size_bytes: 12,
    license: { status: 'confirmed', owner: 'brand' },
    tags: ['brand'],
  },
  {
    asset_id: 'asset-audio',
    revision: 2,
    project_id: 'project-1',
    kind: 'audio',
    content_hash: 'b'.repeat(64),
    relative_object_path: 'workspace-data/assets/b.wav',
    original_name: 'Music.wav',
    mime_type: 'audio/wav',
    size_bytes: 22,
    license: { status: 'unknown' },
    tags: ['music'],
  },
];

describe('AssetLibrary', () => {
  it('filters assets and exposes timeline insertion for visual assets', () => {
    const onOverlay = vi.fn();
    render(<AssetLibrary assets={assets} onSelect={vi.fn()} onCreateOverlay={onOverlay} />);
    fireEvent.change(screen.getByLabelText('搜索素材'), { target: { value: 'logo' } });
    expect(screen.getByText('Logo.png')).toBeInTheDocument();
    expect(screen.queryByText('Music.wav')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '放入时间线' }));
    expect(onOverlay).toHaveBeenCalledWith(assets[0]);
  });
});
