import { expect, test } from '@playwright/test';

test('human presenter anchor lock survives refresh', async ({ page }) => {
  const pageErrors: string[] = [];
  page.on('pageerror', (error) => pageErrors.push(error.message));
  const project = {
    schema_version: 1,
    id: 'project-1',
    name: 'Presenter review',
    project_dir: 'presenter-review',
    created_at: '2026-08-10T00:00:00Z',
    updated_at: '2026-08-10T00:00:00Z',
    current_step: 5,
    status: 'running',
    pages: [],
    jobs: [],
    source_files: [],
    audit_log: [],
    matches: [],
    presentation_mode: 'human_presenter',
    presenter_source: {
      id: 'source-1',
      relative_path: 'presenter/source.mp4',
      sha256: 'a'.repeat(64),
      duration_ms: 2000,
      media_type: 'video/mp4',
      probe_snapshot: {},
      imported_at: null,
    },
    presenter_timeline: {
      schema_version: '1.0',
      revision: 3,
      source_id: 'source-1',
      source_version: 'a'.repeat(64),
      duration_ms: 2000,
      anchors: [
        {
          page_id: '00000000-0000-0000-0000-000000000001',
          start_ms: 0,
          end_ms: 2000,
          sentence_ids: ['s1'],
          confidence: 0.95,
          status: 'auto',
          manual_lock: false,
          source_revision: 'a'.repeat(64),
        },
      ],
      segments: [],
      unassigned_ranges: [],
      timeline_hash: 'b'.repeat(64),
      generated_at: null,
    },
  };

  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (!url.pathname.startsWith('/api/')) return route.continue();
    let data: unknown;
    if (url.pathname === '/api/projects/project-1' && request.method() === 'GET') {
      data = project;
    } else if (url.pathname === '/api/system/disk') {
      data = { total: 1000, used: 400, free: 600 };
    } else if (url.pathname.endsWith('/audio/gate')) {
      data = { allowed: false, reasons: [] };
    } else if (
      url.pathname.includes('/presenter-timeline/anchors/') &&
      request.method() === 'PATCH'
    ) {
      project.presenter_timeline.revision += 1;
      project.presenter_timeline.timeline_hash = 'c'.repeat(64);
      project.presenter_timeline.anchors[0].manual_lock = true;
      project.presenter_timeline.anchors[0].status = 'confirmed';
      data = project;
    } else {
      return route.abort();
    }
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data, error: null, request_id: 'e2e' }),
    });
  });

  await page.goto('/projects/project-1/step/5');
  await page.waitForTimeout(500);
  expect(pageErrors, await page.locator('body').innerText()).toEqual([]);
  await expect(page.getByRole('heading', { name: '真人讲解' })).toBeVisible();
  await page.getByRole('button', { name: '保存并锁定' }).click();
  await expect(page.getByText('第 1 页 · 已锁定')).toBeVisible();
  await page.reload();
  await expect(page.getByText('第 1 页 · 已锁定')).toBeVisible();
  await expect(page.getByText(/^r4/)).toBeVisible();
});
