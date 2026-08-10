import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { api } from '../../../api/client';
import { StoragePanel } from './StoragePanel';

vi.mock('../../../api/client', () => ({
  api: {
    estimateCleanup: vi.fn(),
    executeCleanup: vi.fn(),
  },
}));

describe('StoragePanel', () => {
  it('shows estimate, protected paths, and requires a second confirmation', async () => {
    vi.mocked(api.estimateCleanup).mockResolvedValue({
      id: 'plan-1',
      project_id: 'project-1',
      relative_paths: ['07_视频工程/segments/page-1.mp4'],
      bytes_reclaimable: 2048,
      affected_nodes: ['segment:page-1', 'final'],
      protected_paths: ['project.json', '08_输出/最终视频.mp4'],
      confirmation_token: 'token-1',
      created_at: '2026-08-04T00:00:00Z',
    });
    vi.mocked(api.executeCleanup).mockResolvedValue({
      plan_id: 'plan-1',
      deleted_paths: ['07_视频工程/segments/page-1.mp4'],
      bytes_reclaimed: 2048,
      affected_nodes: ['segment:page-1', 'final'],
    });

    render(<StoragePanel projectId="project-1" />);
    fireEvent.click(screen.getByRole('button', { name: '估算可清理缓存' }));

    expect(await screen.findByText('2.0 KB')).toBeInTheDocument();
    expect(screen.getByText(/受保护：project\.json/)).toBeInTheDocument();
    const execute = screen.getByRole('button', { name: '确认并清理' });
    expect(execute).toBeDisabled();

    fireEvent.click(screen.getByLabelText('我确认删除可重建缓存'));
    fireEvent.click(execute);
    await waitFor(() => expect(api.executeCleanup).toHaveBeenCalledWith('project-1', 'plan-1', 'token-1'));
    expect(await screen.findByText('已释放 2.0 KB')).toBeInTheDocument();
  });
});
