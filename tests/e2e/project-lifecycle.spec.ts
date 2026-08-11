import { expect, test } from '@playwright/test';

type MockRenderJob = {
  id: string;
  status: string;
  revision: number;
  [key: string]: unknown;
};

test('project lifecycle survives browser close and reload', async ({ browser, page }) => {
  const name = `中文项目-${Date.now()}`;
  await page.goto('/');
  await expect(page.getByRole('heading', { name: '项目中心' })).toBeVisible();

  await page.getByLabel('项目名称').fill(name);
  await page.getByRole('button', { name: '创建项目' }).click();
  await expect(page.getByRole('heading', { name })).toBeVisible();
  await expect(page.getByText(/当前项目目录：中文项目-/)).toBeVisible();

  const projectUrl = page.url();
  await page.close();
  const reopened = await browser.newPage();
  await reopened.goto('/');
  await reopened.getByRole('button', { name: new RegExp(name) }).click();
  await expect(reopened).toHaveURL(projectUrl);

  await reopened.getByRole('button', { name: '第4步 逐页旁白校对' }).click();
  await expect(reopened.getByRole('button', { name: '第4步 逐页旁白校对' })).toHaveAttribute(
    'aria-current',
    'step',
  );
  await reopened.reload();
  await expect(reopened.getByRole('button', { name: '第4步 逐页旁白校对' })).toHaveAttribute(
    'aria-current',
    'step',
  );

  await reopened.getByRole('button', { name: '暂停项目' }).click();
  await expect(reopened.getByRole('button', { name: '继续项目' })).toBeVisible();
  await reopened.getByRole('button', { name: '继续项目' }).click();
  await expect(reopened.getByRole('button', { name: '暂停项目' })).toBeVisible();
});

test('async render job survives reload and pause/resume', async ({ page }) => {
  const name = `异步渲染项目-${Date.now()}`;
  await page.goto('/');
  await page.getByLabel('项目名称').fill(name);
  await page.getByRole('button', { name: '创建项目' }).click();
  await expect(page.getByRole('heading', { name })).toBeVisible();

  const projectId = new URL(page.url()).pathname.split('/')[2];
  const jobId = `e2e-render-job-${Date.now()}`;
  const timestamps = {
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
  let currentJob: MockRenderJob = {
    id: jobId,
    project_id: projectId,
    job_type: 'export_package',
    status: 'running',
    progress: 0.4,
    attempts: 1,
    max_attempts: 3,
    stage: 'rendering_pages',
    message: '正在渲染第 1 页',
    error: null,
    error_code: null,
    revision: 2,
    ...timestamps,
    heartbeat_at: timestamps.updated_at,
    started_at: timestamps.created_at,
    finished_at: null,
    result: null,
  };
  const observedJobIds = new Set<string>();
  let currentRequests = 0;

  await page.route(`**/api/projects/${projectId}`, async (route) => {
    if (route.request().method() !== 'GET') {
      await route.fallback();
      return;
    }
    const response = await route.fetch();
    const envelope = (await response.json()) as { data: { current_step: number; status: string } };
    envelope.data.current_step = 7;
    envelope.data.status = 'running';
    await route.fulfill({
      status: response.status(),
      headers: response.headers(),
      body: JSON.stringify(envelope),
    });
  });
  await page.route(`**/api/projects/${projectId}/video/render-jobs/current`, async (route) => {
    currentRequests += 1;
    observedJobIds.add(currentJob.id);
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        data: { job: currentJob },
        error: null,
        request_id: `e2e-render-${currentRequests}`,
      }),
    });
  });
  await page.route(
    `**/api/projects/${projectId}/video/render-jobs/${jobId}/actions`,
    async (route) => {
      const payload = route.request().postDataJSON() as { action: string };
      if (payload.action === 'pause') {
        currentJob = {
          ...currentJob,
          status: 'paused',
          stage: 'paused',
          message: '任务已暂停，可继续渲染',
          revision: currentJob.revision + 1,
        };
      } else if (payload.action === 'resume') {
        currentJob = {
          ...currentJob,
          status: 'succeeded',
          progress: 1,
          stage: 'completed',
          message: '渲染与制作包导出已完成',
          revision: currentJob.revision + 1,
          finished_at: new Date().toISOString(),
          result: {
            mp4_relative_path: 'renders/final.mp4',
            package_relative_path: 'packages/final.zip',
            duration_ms: 2400,
            width: 1920,
            height: 1080,
            video_codec: 'h264',
            audio_codec: 'aac',
            artifact_count: 4,
            cached_pages: 1,
          },
        };
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          data: { job: currentJob, created: false },
          error: null,
          request_id: `e2e-render-action-${currentJob.revision}`,
        }),
      });
    },
  );

  await page.goto(`/projects/${projectId}/step/7`);
  await expect(page.getByRole('heading', { name: '渲染与导出' })).toBeVisible();
  await expect(page.getByText('渲染中', { exact: true })).toBeVisible();

  await page.reload();
  await expect(page.getByText('渲染中', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await expect(page.getByText('已暂停', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '继续' }).click();
  await expect(page.getByText('已完成', { exact: true })).toBeVisible();
  await expect(page.getByText(/成片：renders\/final\.mp4/)).toBeVisible();
  await expect(page.getByText(/制作包：packages\/final\.zip/)).toBeVisible();

  expect([...observedJobIds]).toEqual([jobId]);
  expect(currentRequests).toBeGreaterThanOrEqual(2);
});
