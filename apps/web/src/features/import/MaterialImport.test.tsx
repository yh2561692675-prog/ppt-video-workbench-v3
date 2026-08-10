import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { MaterialImport } from './MaterialImport';

const source = (id: string, name: string, order: number) => ({
  id,
  kind: 'image' as const,
  original_name: name,
  safe_name: name,
  copied_path: `01_源文件/${name}`,
  sha256: 'a'.repeat(64),
  size: 10,
  modified_at: '2026-08-03T00:00:00Z',
  image_order: order,
});

describe('material import', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('uploads a batch, reports progress and exposes manual image ordering', async () => {
    const imported = [source('1', '第1页.png', 1), source('2', '第2页.png', 2)];
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async () =>
          new Response(
            JSON.stringify({
              data: imported,
              error: null,
              request_id: 'request-1',
            }),
            { headers: { 'Content-Type': 'application/json' } },
          ),
      ),
    );
    render(<MaterialImport projectId="project-1" initialSources={[]} />);

    const input = screen.getByLabelText('选择材料文件');
    fireEvent.change(input, {
      target: { files: [new File(['one'], '第2页.png'), new File(['two'], '第1页.png')] },
    });
    fireEvent.click(screen.getByRole('button', { name: '开始导入' }));

    expect(await screen.findByText('已导入 2 个文件')).toBeInTheDocument();
    expect(screen.getByText('第1页.png').closest('li')).toHaveAttribute('draggable', 'true');
    fireEvent.click(screen.getByRole('button', { name: '下移 第1页.png' }));

    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    const secondRequest = vi.mocked(fetch).mock.calls[1];
    expect(String(secondRequest[0])).toContain('/sources/image-order');
  });
});
