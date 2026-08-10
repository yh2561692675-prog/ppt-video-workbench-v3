import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';

import { ProjectCenter } from './ProjectCenter';

afterEach(() => vi.unstubAllGlobals());

it('offers a direct HeyGen settings entry alongside model settings', async () => {
  vi.stubGlobal(
    'fetch',
    async () =>
      new Response(JSON.stringify({ data: [], error: null, request_id: 'request-1' }), {
        headers: { 'Content-Type': 'application/json' },
      }),
  );

  render(
    <QueryClientProvider client={new QueryClient()}>
      <BrowserRouter>
        <ProjectCenter />
      </BrowserRouter>
    </QueryClientProvider>,
  );

  expect(
    await screen.findByRole('link', { name: 'HeyGen 声音设置' }),
  ).toHaveAttribute('href', '/settings/heygen');
  expect(screen.getByRole('link', { name: '模型接口设置' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: '一键健康检查' })).toHaveAttribute(
    'href',
    '/diagnostics',
  );
});
