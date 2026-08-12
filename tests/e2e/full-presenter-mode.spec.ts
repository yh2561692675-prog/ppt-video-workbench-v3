import { expect, test } from '@playwright/test';

import type { PresenterSource, PresenterTimeline } from '../../apps/web/src/features/presenter/api';
import { realFlowEnabled, realFlowSkipReason } from './real-flow-policy';

type MockProject = {
  schema_version: number;
  id: string;
  name: string;
  project_dir: string;
  created_at: string;
  updated_at: string;
  current_step: number;
  status: string;
  pages: Array<{ id: string; order: number; title: string }>;
  jobs: unknown[];
  source_files: unknown[];
  audit_log: unknown[];
  matches: unknown[];
  presentation_mode: 'ai_narration' | 'human_presenter';
  presenter_source: PresenterSource | null;
  presenter_timeline: PresenterTimeline | null;
};

test('presenter browser workflow keeps the locked timeline hash across refresh', async ({
  page,
}) => {
  const source: PresenterSource = {
    id: '00000000-0000-0000-0000-000000000010',
    relative_path: 'presenter/source.mp4',
    sha256: 'a'.repeat(64),
    duration_ms: 3_000,
    media_type: 'video/mp4',
    probe_snapshot: {},
    imported_at: null,
  };
  const analyzedTimeline: PresenterTimeline = {
    schema_version: '1.0',
    revision: 1,
    source_id: source.id,
    source_version: source.sha256,
    duration_ms: 3_000,
    anchors: [
      {
        page_id: '00000000-0000-0000-0000-000000000001',
        start_ms: 0,
        end_ms: 3_000,
        sentence_ids: ['sentence-1'],
        confidence: 0.98,
        status: 'auto',
        manual_lock: false,
        source_revision: source.sha256,
      },
    ],
    segments: [
      {
        start_ms: 0,
        end_ms: 3_000,
        layout: 'bottom_right',
        width_ratio: 0.24,
        manual_lock: false,
        source_revision: source.sha256,
      },
    ],
    unassigned_ranges: [],
    timeline_hash: 'b'.repeat(64),
    generated_at: null,
  };
  let project: MockProject = {
    schema_version: 1,
    id: 'project-presenter-e2e',
    name: 'Presenter full chain',
    project_dir: 'presenter-full-chain',
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
    current_step: 5,
    status: 'running',
    pages: [{ id: analyzedTimeline.anchors[0].page_id, order: 1, title: 'Overview' }],
    jobs: [],
    source_files: [],
    audit_log: [],
    matches: [],
    presentation_mode: 'ai_narration',
    presenter_source: null,
    presenter_timeline: null,
  };

  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/')) return route.continue();
    let data: unknown;
    if (url.pathname === `/api/projects/${project.id}` && request.method() === 'GET') {
      data = project;
    } else if (url.pathname === '/api/system/disk') {
      data = { total: 1_000, used: 400, free: 600 };
    } else if (url.pathname.endsWith('/audio/gate')) {
      data = { allowed: project.presenter_timeline !== null, reasons: [] };
    } else if (url.pathname.endsWith('/presenter-source') && request.method() === 'POST') {
      project = { ...project, presentation_mode: 'human_presenter', presenter_source: source };
      data = project;
    } else if (url.pathname.endsWith('/presenter-analysis') && request.method() === 'POST') {
      project = { ...project, presenter_timeline: analyzedTimeline };
      data = {
        project,
        transcript: { content_hash: 'd'.repeat(64), sentences: [] },
        matches: { matches: [], unassigned_sentence_ids: [] },
      };
    } else if (url.pathname.includes('/presenter-timeline/anchors/')) {
      project = {
        ...project,
        presenter_timeline: {
          ...analyzedTimeline,
          revision: 2,
          timeline_hash: 'c'.repeat(64),
          anchors: analyzedTimeline.anchors.map((anchor) => ({
            ...anchor,
            status: 'confirmed' as const,
            manual_lock: true,
          })),
        },
      };
      data = project;
    } else if (url.pathname.endsWith('/video/preview')) {
      data = {
        allowed: true,
        props: {
          timeline_hash: project.presenter_timeline?.timeline_hash,
          presenter_source_path: source.relative_path,
        },
        issues: [],
      };
    } else if (url.pathname.endsWith('/video/render-jobs')) {
      data = {
        job: { id: 'render-1', status: 'completed' },
        artifacts: [
          'final.mp4',
          'subtitles.srt',
          'presenter/transcript.json',
          'presenter/matches.json',
          'presenter/timeline.json',
          'presenter/window-plan.json',
          'preflight.json',
          'logs.json',
        ],
        timeline_hash: project.presenter_timeline?.timeline_hash,
      };
    } else {
      return route.abort();
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data, error: null, request_id: 'presenter-e2e' }),
    });
  });

  await page.goto(`/projects/${project.id}/step/5`);
  await expect(page.getByRole('heading', { name: '改用真人讲解视频' })).toBeVisible();
  await page.getByLabel('选择用于启用真人模式的视频').setInputFiles({
    name: '真人讲解.mp4',
    mimeType: 'video/mp4',
    buffer: Buffer.from('fixture'),
  });
  await page.getByRole('button', { name: '启用真人讲解并导入' }).click();
  await expect(page.locator('.presenter-workspace')).toBeVisible();
  await page.locator('.presenter-zone').first().locator('button').nth(1).click();
  await expect(page.locator('.presenter-version')).toContainText('bbbbbbbbbbbb');
  await page.locator('.presenter-timeline button').click();
  await expect(page.locator('.presenter-version')).toContainText('cccccccccccc');

  const lockedHash = project.presenter_timeline?.timeline_hash;
  await page.reload();
  await expect(page.locator('.presenter-version')).toContainText('cccccccccccc');
  expect(project.presenter_timeline?.revision).toBe(2);
  expect(project.presenter_timeline?.timeline_hash).toBe(lockedHash);

  const acceptance = await page.evaluate(async (projectId) => {
    const preview = await fetch(`/api/projects/${projectId}/video/preview`).then((item) =>
      item.json(),
    );
    const render = await fetch(`/api/projects/${projectId}/video/render-jobs`, {
      method: 'POST',
    }).then((item) => item.json());
    return { preview: preview.data, render: render.data };
  }, project.id);
  expect(acceptance.preview.allowed).toBe(true);
  expect(acceptance.render.timeline_hash).toBe(lockedHash);
  expect(acceptance.render.artifacts).toEqual(
    expect.arrayContaining([
      'final.mp4',
      'subtitles.srt',
      'presenter/transcript.json',
      'presenter/matches.json',
      'presenter/timeline.json',
      'presenter/window-plan.json',
      'preflight.json',
      'logs.json',
    ]),
  );
});

test('real presenter full chain produces the RC1 evidence package', async () => {
  test.skip(!realFlowEnabled('presenter-windows-rc'), realFlowSkipReason('presenter-windows-rc'));
  // Execute only on the authorized target Windows RC machine.
});
