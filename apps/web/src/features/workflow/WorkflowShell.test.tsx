import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';

import { AudioAsset, AudioImportRecord, Project } from '../../api/client';
import { WorkflowShell } from './WorkflowShell';

vi.mock('../video/PreviewWorkspace', () => ({ PreviewWorkspace: () => null }));

afterEach(() => vi.unstubAllGlobals());

const page = {
  id: 'page-1',
  order: 1,
  title: '开场',
  narration: {
    revision_id: 'revision-1',
    text: '第一页旁白',
    version: 1,
    source_refs: [],
    status: 'completed' as const,
  },
};

const project: Project = {
  schema_version: 1,
  id: 'project-1',
  name: '路线互斥测试',
  project_dir: 'route-test',
  created_at: '2026-08-05T00:00:00Z',
  updated_at: '2026-08-05T00:00:00Z',
  current_step: 5,
  status: 'running',
  pages: [page],
  jobs: [],
  source_files: [],
  audit_log: [],
  matches: [],
};

const importedAudio: AudioImportRecord = {
  id: 'audio-1',
  original_relative_path: 'audio/local.mp3',
  normalized_relative_path: 'audio/local.normalized.wav',
  duration_ms: 1200,
  sample_rate: 16000,
  channels: 1,
  sha256: 'a'.repeat(64),
  peak_dbfs: -2,
  silence_ratio: 0,
  silence_intervals_ms: [],
  needs_confirmation: false,
  imported_at: '2026-08-05T00:00:00Z',
};

const generatedAudio: AudioAsset = {
  page_id: 'page-1',
  relative_path: 'audio/page-1.mp3',
  duration_ms: 1200,
  source: 'heygen',
  cache_key: 'cache-1',
  voice_id: 'voice-1',
  request_id: 'request-1',
  cached: false,
};

function response(data: unknown) {
  return new Response(JSON.stringify({ data, error: null, request_id: 'request-1' }), {
    headers: { 'Content-Type': 'application/json' },
  });
}

function installFetch(
  currentProject: Project,
  synthesize: () => Promise<Response> = async () => response(generatedAudio),
) {
  const fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url === '/api/projects/project-1' && (!init?.method || init.method === 'GET')) {
      return response(currentProject);
    }
    if (url === '/api/system/disk') return response({ total: 1000, used: 400, free: 600 });
    if (url === '/api/projects/project-1/audio/gate') {
      return response({ allowed: false, reasons: [] });
    }
    if (url === '/api/settings/heygen-profiles') {
      return response([
        {
          id: 'profile-1',
          name: 'Studio voice',
          base_url: 'https://api.heygen.com',
          base_url_digest: 'digest',
          has_api_key: true,
          created_at: '2026-08-05T00:00:00Z',
          updated_at: '2026-08-05T00:00:00Z',
          last_used_at: null,
        },
      ]);
    }
    if (url === '/api/settings/heygen-profiles/profile-1/voices') {
      return response([
        {
          voice_id: 'voice-1',
          name: 'Narrator',
          language: 'zh-CN',
          gender: 'female',
          support_pause: true,
          support_locale: true,
          preview_audio_url: null,
        },
      ]);
    }
    if (url === '/api/projects/project-1/audio/import' && init?.method === 'POST') {
      return response(importedAudio);
    }
    if (url === '/api/projects/project-1/audio/heygen/page-1' && init?.method === 'POST') {
      return synthesize();
    }
    throw new Error(`unexpected request ${url}`);
  });
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

function renderWorkflow() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/projects/project-1/step/5']}>
        <Routes>
          <Route path="/projects/:projectId/step/:step" element={<WorkflowShell />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function selectProfileAndVoice() {
  fireEvent.change(await screen.findByLabelText('HeyGen 配置'), {
    target: { value: 'profile-1' },
  });
  await screen.findByRole('option', { name: 'Narrator（zh-CN）' });
  fireEvent.change(screen.getByLabelText('声音'), { target: { value: 'voice-1' } });
}

it('immediately disables HeyGen after local import even while project refetch remains stale', async () => {
  installFetch(project);
  renderWorkflow();
  await selectProfileAndVoice();
  expect(screen.getByRole('button', { name: '使用 HeyGen 生成全部页面配音' })).toBeEnabled();

  fireEvent.change(screen.getByLabelText('选择本地录音'), {
    target: { files: [new File(['audio'], 'local.mp3', { type: 'audio/mpeg' })] },
  });
  fireEvent.click(screen.getByRole('button', { name: '导入并规范化' }));

  expect(
    await screen.findByText('已导入本地录音，不能同时使用 HeyGen 页面配音。'),
  ).toBeInTheDocument();
  expect(screen.getByRole('button', { name: '使用 HeyGen 生成全部页面配音' })).toBeDisabled();
});

it('disables local import when a HeyGen batch starts and keeps it disabled after success', async () => {
  let releaseSynthesis!: (value: Response) => void;
  const synthesis = new Promise<Response>((resolve) => {
    releaseSynthesis = resolve;
  });
  installFetch(project, () => synthesis);
  renderWorkflow();
  fireEvent.change(await screen.findByLabelText('选择本地录音'), {
    target: { files: [new File(['audio'], 'local.mp3', { type: 'audio/mpeg' })] },
  });
  await selectProfileAndVoice();

  fireEvent.click(screen.getByRole('button', { name: '使用 HeyGen 生成全部页面配音' }));

  await waitFor(() => expect(screen.getByLabelText('选择本地录音')).toBeDisabled());
  expect(screen.getByText('HeyGen 页面配音路线已启用，不能同时导入本地录音。')).toBeInTheDocument();
  releaseSynthesis(response(generatedAudio));
  expect(await screen.findByText('全部 1 页 HeyGen 配音已生成。')).toBeInTheDocument();
  expect(screen.getByLabelText('选择本地录音')).toBeDisabled();
});

it('restores the HeyGen route from completed page audio after a project reload', async () => {
  const persistedProject: Project = {
    ...project,
    pages: [
      {
        ...page,
        audio: {
          id: 'page-audio-1',
          status: 'completed',
          source: 'heygen',
          relative_path: 'audio/page-1.mp3',
          duration_ms: 1200,
          cache_key: 'cache-1',
          narration_revision_id: 'revision-1',
          voice_id: 'voice-1',
          remote_request_id: 'request-1',
        },
      },
    ],
  };
  installFetch(persistedProject);
  renderWorkflow();

  expect(await screen.findByLabelText('选择本地录音')).toBeDisabled();
  expect(screen.getByText('HeyGen 页面配音路线已启用，不能同时导入本地录音。')).toBeInTheDocument();
});
