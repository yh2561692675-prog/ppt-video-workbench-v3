import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { App } from './App';

const project = {
  schema_version: 1,
  id: '4a5569d0-1c80-4d35-a4ee-2d7af3d603c2',
  name: '计算机类专业介绍',
  project_dir: '计算机类专业介绍_20260803_1630',
  created_at: '2026-08-03T08:30:00Z',
  updated_at: '2026-08-03T08:30:00Z',
  current_step: 1,
  status: 'not_started',
  pages: [],
  jobs: [],
  source_files: [],
  audit_log: [],
  matches: [],
};

describe('project lifecycle workbench shell', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      let data: unknown = null;
      if (url.endsWith('/api/projects') && (!init?.method || init.method === 'GET')) data = [];
      if (url.endsWith('/api/system/disk')) data = { total: 1000, used: 400, free: 600 };
      if (url.endsWith('/api/projects') && init?.method === 'POST') data = project;
      if (url.includes(`/api/projects/${project.id}`) && (!init?.method || init.method === 'GET')) {
        data = project;
      }
      if (url.endsWith('/step')) data = { ...project, current_step: 4 };
      if (url.endsWith('/pause')) data = { ...project, current_step: 4, status: 'paused' };
      if (url.endsWith('/resume')) data = { ...project, current_step: 4, status: 'not_started' };
      return new Response(JSON.stringify({ data, error: null, request_id: 'request-1' }), {
        headers: { 'Content-Type': 'application/json' },
      });
    });
  });

  afterEach(() => vi.unstubAllGlobals());

  it('creates a project and controls its seven-step workflow', async () => {
    render(<App />);

    expect(await screen.findByRole('heading', { name: '项目中心' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('项目名称'), {
      target: { value: '计算机类专业介绍' },
    });
    fireEvent.click(screen.getByRole('button', { name: '创建项目' }));

    expect(
      await screen.findByRole('heading', { name: '计算机类专业介绍' }, { timeout: 5000 }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /第\d步/ })).toHaveLength(7);
    expect(screen.getByText('可用磁盘 600 B')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: '第4步 逐页旁白校对' }));
    await waitFor(() =>
      expect(screen.getByRole('button', { name: '第4步 逐页旁白校对' })).toHaveAttribute(
        'aria-current',
        'step',
      ),
    );

    fireEvent.click(screen.getByRole('button', { name: '暂停项目' }));
    expect(await screen.findByRole('button', { name: '继续项目' })).toBeInTheDocument();
  });

  it('warns before leaving when a new project name is unsaved', async () => {
    render(<App />);
    await screen.findByRole('heading', { name: '项目中心' });
    fireEvent.change(screen.getByLabelText('项目名称'), { target: { value: '尚未保存' } });
    const event = new Event('beforeunload', { cancelable: true });

    window.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
  });
});
