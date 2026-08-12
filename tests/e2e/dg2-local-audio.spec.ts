import {
  expect,
  test,
  type APIRequestContext,
  type Page,
  type TestInfo,
} from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { writeFile } from 'node:fs/promises';
import path from 'node:path';

const apiBaseUrl = 'http://127.0.0.1:8765';
const fixtureRoot = path.resolve('tests/.e2e-fixtures');

type FixtureProfile = 'S1' | 'S8';

interface PublishedArtifacts {
  mp4_relative_path: string;
  package_relative_path: string;
}

interface CurrentRenderJob {
  id: string;
  status: string;
  revision: number;
  result: PublishedArtifacts | null;
}

interface CurrentProject {
  current_step: number;
  pages: Array<{ id: string }>;
}

test.describe.configure({ mode: 'serial' });

for (const profile of ['S1', 'S8'] as const) {
  test(`${profile} browser local-audio workflow exports an auditable production package`, async ({
    page,
    request,
  }, testInfo) => {
    test.setTimeout(profile === 'S8' ? 240_000 : 300_000);
    const evidence = installFailureEvidence(page, testInfo, profile);
    const projectName = `DG2 ${profile} 合成验收 ${Date.now()}`;

    await page.goto('/');
    await expect(page.getByRole('heading', { name: '项目中心' })).toBeVisible();
    await page.getByLabel('项目名称').fill(projectName);
    await page.getByRole('button', { name: '创建项目' }).click();
    await expect(page.getByRole('heading', { name: projectName })).toBeVisible();
    const projectId = projectIdFrom(page.url());

    await page.getByRole('button', { name: '第2步 导入材料' }).click();
    await page.getByLabel('选择材料文件').setInputFiles([
      path.join(fixtureRoot, profile.toLowerCase(), 'outline.docx'),
      path.join(fixtureRoot, profile.toLowerCase(), 'deck.pptx'),
    ]);
    await page.getByRole('button', { name: '开始导入' }).click();
    await expect(page.getByRole('status')).toContainText('已导入 2 个文件');

    await page.getByRole('button', { name: '第3步 材料解析与匹配' }).click();
    await page.getByRole('button', { name: '开始解析与匹配' }).click();
    await expect(page.locator('.match-card')).toHaveCount(profile === 'S1' ? 2 : 8, {
      timeout: 60_000,
    });

    await page.getByRole('button', { name: '第4步 逐页旁白校对' }).click();
    const editors = page.locator('.narration-editor');
    const pageCount = profile === 'S1' ? 2 : 8;
    await expect(editors).toHaveCount(pageCount);
    for (let index = 0; index < pageCount; index += 1) {
      const editor = editors.nth(index);
      await editor.getByLabel('旁白正文').fill(`合成第${index + 1}页旁白`);
      await editor.getByRole('button', { name: '保存新版本' }).click();
      await expect(editor).toContainText('版本 1');
    }
    await page.reload();
    await page.getByRole('button', { name: '查看批量确认摘要' }).click();
    await page.getByRole('button', { name: '确认全部当前版本' }).click();
    await expect(page.getByText(`已确认 ${pageCount} 页`)).toBeVisible();

    await page.getByRole('button', { name: '第5步 配音与音频对齐' }).click();
    await page.getByLabel('选择本地录音').setInputFiles(
      path.join(fixtureRoot, profile.toLowerCase(), 'local-narration.wav'),
    );
    await page.getByRole('button', { name: '导入并规范化' }).click();
    await expect(page.getByText('录音已导入并规范化', { exact: true })).toBeVisible({
      timeout: 30_000,
    });
    await page.getByRole('button', { name: '转写本地录音' }).click();
    await expect(page.getByText('本地转写已完成', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '检查旁白差异' }).click();
    await expect(page.getByText('差异检查已完成', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: '自动分页' }).click();
    await expect(page.getByText('自动分页已完成', { exact: true })).toBeVisible();
    await expect(page.getByText('音频门禁已通过，可进入字幕步骤。')).toBeVisible();
    await page.getByRole('button', { name: '生成字幕' }).click();
    await expect(page.getByText('字幕时间轴与 SRT 已生成', { exact: true })).toBeVisible();
    if (profile === 'S1') {
      await initializeTimeline(request, projectId, pageCount);
      await registerConfirmedTimelineAssets(request, projectId, pageCount);
    }

    await page.getByRole('button', { name: '第6步 效果预览与完整预检' }).click();
    await expect(page.getByRole('heading', { name: '效果预览与完整预检', level: 2 })).toBeVisible();
    if (profile === 'S1') {
      await assertTimelineConflict(page, request, projectId, pageCount);
      await assertAuthoritativePreviewToEnd(page, projectId, pageCount);
    }
    await page.getByRole('button', { name: /生成缺失计划/ }).click();
    await expect(page.locator('.effect-page-status .status-pill')).toHaveCount(pageCount);
    await page.getByRole('button', { name: '重新运行完整预检' }).click();
    await expect(page.getByText('完整预检已通过')).toBeVisible();
    await page.getByRole('button', { name: '开始渲染与导出' }).first().click();
    await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/step/7`));
    await expect
      .poll(async () => currentProjectStep(request, projectId), { timeout: 30_000 })
      .toBe(7);
    const initialJob = await waitForRenderStatus(request, projectId, ['running', 'pause_requested']);
    if (profile === 'S1') {
      await assertDuplicateRenderSubmission(request, projectId, initialJob.id);
      await cancelAndRetryRender(page, request, projectId);
    } else {
      await pauseAndResumeRender(page, request, projectId);
    }
    await waitForCompletedRenderJob(request, projectId);
    await expect(page.getByText('已完成', { exact: true })).toBeVisible();

    const job = await currentRenderJob(request, projectId);
    const jobId = job.id;
    expect(job.result).not.toBeNull();
    await page.reload();
    await expect(page.getByText('已完成', { exact: true })).toBeVisible();

    await assertPublishedArtifacts(request, projectId, pageCount, job.result!);
    await assertRefreshUsesSameJob(page, request, projectId, jobId);
    await evidence.flush();
    await attachSuccessfulBrowserEvidence(page, testInfo, profile, projectId, jobId);
    // `page` and `request` are Playwright fixtures.  Let its managed teardown
    // close the Edge media context and API client exactly once; explicit
    // closing here can leave the worker waiting on a second teardown cycle.
  });
}

async function assertPublishedArtifacts(
  request: APIRequestContext,
  projectId: string,
  pageCount: number,
  artifacts: PublishedArtifacts,
): Promise<void> {
  const mp4 = await request.get(
    `${apiBaseUrl}/api/projects/${projectId}/video/assets/${artifacts.mp4_relative_path}`,
  );
  expect(mp4.ok()).toBeTruthy();
  expect((await mp4.body()).subarray(4, 8).toString('ascii')).toBe('ftyp');
  const srt = await request.get(
    `${apiBaseUrl}/api/projects/${projectId}/video/assets/${artifacts.package_relative_path}/字幕.srt`,
  );
  expect(srt.ok()).toBeTruthy();
  expect(await srt.text()).toContain('合成第');
  const manifest = await request.get(
    `${apiBaseUrl}/api/projects/${projectId}/video/assets/${artifacts.package_relative_path}/制作包清单.json`,
  );
  expect(manifest.ok()).toBeTruthy();
  const parsed = JSON.parse(await manifest.text()) as { artifacts: Array<{ relative_path: string }> };
  expect(parsed.artifacts).toEqual(
    expect.arrayContaining([
      expect.objectContaining({ relative_path: '最终视频.mp4' }),
      expect.objectContaining({ relative_path: '字幕.srt' }),
      expect.objectContaining({ relative_path: `分页音频/page-${String(pageCount).padStart(4, '0')}.wav` }),
    ]),
  );
}

async function assertRefreshUsesSameJob(
  page: Page,
  request: APIRequestContext,
  projectId: string,
  jobId: string,
): Promise<void> {
  const reopened = await page.context().newPage();
  try {
    await reopened.goto(`/projects/${projectId}/step/7`);
    await expect(reopened).toHaveURL(new RegExp(`/projects/${projectId}/step/7`));
    await expect(reopened.getByText('已完成', { exact: true })).toBeVisible();
    expect(await currentRenderJobId(request, projectId)).toBe(jobId);
  } finally {
    await reopened.close();
  }
}

async function currentRenderJobId(request: APIRequestContext, projectId: string): Promise<string> {
  return (await currentRenderJob(request, projectId)).id;
}

async function currentRenderJob(
  request: APIRequestContext,
  projectId: string,
): Promise<CurrentRenderJob> {
  const response = await request.get(
    `${apiBaseUrl}/api/projects/${projectId}/video/render-jobs/current`,
  );
  expect(response.ok()).toBeTruthy();
  const payload = (await response.json()) as { data: { job: CurrentRenderJob | null } | null };
  const job = payload.data?.job;
  expect(job?.id ?? '').toMatch(/^[0-9a-f-]{36}$/i);
  expect(job).not.toBeNull();
  return job!;
}

async function currentProjectStep(request: APIRequestContext, projectId: string): Promise<number> {
  return (await currentProject(request, projectId)).current_step;
}

async function currentProject(request: APIRequestContext, projectId: string): Promise<CurrentProject> {
  const response = await request.get(`${apiBaseUrl}/api/projects/${projectId}`);
  expect(response.ok()).toBeTruthy();
  const payload = (await response.json()) as { data: CurrentProject | null };
  expect(payload.data).not.toBeNull();
  return payload.data!;
}

async function initializeTimeline(
  request: APIRequestContext,
  projectId: string,
  pageCount: number,
): Promise<void> {
  const project = await currentProject(request, projectId);
  expect(project.pages).toHaveLength(pageCount);
  const slideTrackId = randomUUID();
  const narrationTrackId = randomUUID();
  const response = await request.post(`${apiBaseUrl}/api/projects/${projectId}/timeline/initialize`, {
    data: {
      project_id: projectId,
      duration_us: pageCount * 750_000,
      tracks: [
        {
          id: slideTrackId,
          kind: 'slide',
          name: 'DG2 Slides',
          order: 0,
          clips: project.pages.map((item, index) => ({
            id: randomUUID(),
            track_id: slideTrackId,
            kind: 'slide',
            start_us: index * 750_000,
            duration_us: 650_000,
            source_ref: `02_页面预览/page-${String(index + 1).padStart(4, '0')}.png`,
            payload: { page_id: item.id },
          })),
        },
        {
          id: narrationTrackId,
          kind: 'narration',
          name: 'DG2 Narration',
          order: 1,
          clips: project.pages.map((item, index) => ({
            id: randomUUID(),
            track_id: narrationTrackId,
            kind: 'narration',
            start_us: index * 750_000,
            duration_us: 750_000,
            source_ref: `05_音频/分页/page-${String(index + 1).padStart(3, '0')}.wav`,
            payload: { page_id: item.id },
          })),
        },
      ],
    },
  });
  expect(response.ok()).toBeTruthy();
}

async function registerConfirmedTimelineAssets(
  request: APIRequestContext,
  projectId: string,
  pageCount: number,
): Promise<void> {
  const assets = Array.from({ length: pageCount }, (_, offset) => {
    const index = offset + 1;
    return [
      {
        relativePath: `02_页面预览/page-${String(index).padStart(4, '0')}.png`,
        kind: 'image',
        mimeType: 'image/png',
      },
      {
        relativePath: `05_音频/分页/page-${String(index).padStart(3, '0')}.wav`,
        kind: 'audio',
        mimeType: 'audio/wav',
      },
    ];
  }).flat();

  for (const asset of assets) {
    const { relativePath, kind, mimeType } = asset;
    const response = await request.post(`${apiBaseUrl}/api/projects/${projectId}/assets/import`, {
      data: {
        relative_path: relativePath,
        original_name: relativePath,
        kind,
        mime_type: mimeType,
        license: {
          status: 'confirmed',
          source: 'DG2 checked-in synthetic fixture',
          owner: 'ppt-video-workbench-v3 test suite',
          license_name: 'Synthetic test fixture',
          license_reference: 'fixtures/dg2/fixture-contract-v1.json',
          project_ids: [projectId],
          confirmed_by: 'DG2 fixture validator',
          confirmed_at: '2026-08-12T00:00:00Z',
        },
      },
    });
    expect(response.ok()).toBeTruthy();
    const payload = (await response.json()) as {
      data: { original_name: string; license: { status: string } } | null;
    };
    expect(payload.data).toMatchObject({
      license: { status: 'confirmed' },
    });
  }
}

async function assertTimelineConflict(
  page: Page,
  request: APIRequestContext,
  projectId: string,
  pageCount: number,
): Promise<void> {
  await page.reload();
  await expect(page.locator('.timeline-workspace')).toBeVisible();
  const secondary = await page.context().newPage();
  try {
    await secondary.goto(`/projects/${projectId}/step/6`);
    await expect(secondary.locator('.timeline-workspace')).toBeVisible();
    const primaryClip = page.locator('.timeline-clip').nth(1);
    await primaryClip.click();
    await page.locator('.timeline-workspace').press('ArrowRight');
    await expect.poll(async () => (await timeline(request, projectId)).revision).toBe(2);

    const staleClip = secondary.locator('.timeline-clip').nth(1);
    await staleClip.click();
    await secondary.locator('.timeline-workspace').press('ArrowRight');
    await expect(secondary.getByRole('alert')).toContainText('时间线已被其他操作更新');
  } finally {
    await secondary.close();
  }

  const current = await timeline(request, projectId);
  expect(current.tracks[0]?.clips).toHaveLength(pageCount);
}

async function assertAuthoritativePreviewToEnd(
  page: Page,
  projectId: string,
  pageCount: number,
): Promise<void> {
  await page.getByRole('button', { name: '编译 RenderGraph' }).click();
  const panel = page.getByLabel('权威区间预览');
  await expect(panel).toBeVisible({ timeout: 30_000 });

  const expectedEndSeconds = (pageCount * 750_000) / 1_000_000;
  await expect(panel.getByLabel('权威预览开始时间')).toHaveValue('0');
  await expect(panel.getByLabel('权威预览结束时间')).toHaveValue(
    String(expectedEndSeconds),
  );
  await panel.getByRole('button', { name: '生成权威预览' }).click();
  await expect(panel.getByText(/任务 succeeded/)).toBeVisible({ timeout: 120_000 });
  const video = panel.getByLabel('权威预览成片');
  await expect(video).toHaveAttribute('src', new RegExp(`/api/projects/${projectId}/video/assets/`));
  await expect(panel.getByText(`${expectedEndSeconds}s`)).toBeVisible();
}

async function timeline(
  request: APIRequestContext,
  projectId: string,
): Promise<{ revision: number; tracks: Array<{ clips: unknown[] }> }> {
  const response = await request.get(`${apiBaseUrl}/api/projects/${projectId}/timeline`);
  expect(response.ok()).toBeTruthy();
  const payload = (await response.json()) as {
    data: { revision: number; tracks: Array<{ clips: unknown[] }> } | null;
  };
  expect(payload.data).not.toBeNull();
  return payload.data!;
}

async function assertDuplicateRenderSubmission(
  request: APIRequestContext,
  projectId: string,
  jobId: string,
): Promise<void> {
  const [first, second] = await Promise.all([
    request.post(`${apiBaseUrl}/api/projects/${projectId}/video/render-jobs`),
    request.post(`${apiBaseUrl}/api/projects/${projectId}/video/render-jobs`),
  ]);
  expect(first.ok()).toBeTruthy();
  expect(second.ok()).toBeTruthy();
  const firstPayload = (await first.json()) as { data: { job: { id: string }; created: boolean } };
  const secondPayload = (await second.json()) as { data: { job: { id: string }; created: boolean } };
  expect(firstPayload.data.job.id).toBe(jobId);
  expect(secondPayload.data.job.id).toBe(jobId);
  expect([firstPayload.data.created, secondPayload.data.created]).toEqual([false, false]);
}

async function cancelAndRetryRender(
  page: Page,
  request: APIRequestContext,
  projectId: string,
): Promise<void> {
  const running = await waitForRenderStatus(request, projectId, ['running', 'pause_requested']);
  await actOnRenderJob(request, projectId, running, 'cancel');
  const cancelled = await waitForRenderStatus(request, projectId, ['cancelled']);
  await page.reload();
  await expect(page.getByRole('button', { name: '重试' })).toBeVisible();
  await page.getByRole('button', { name: '重试' }).click();
  const retried = await waitForRenderStatus(request, projectId, ['queued', 'running', 'pause_requested']);
  expect(retried.id).not.toBe(cancelled.id);
}

async function pauseAndResumeRender(
  page: Page,
  request: APIRequestContext,
  projectId: string,
): Promise<void> {
  const running = await waitForRenderStatus(request, projectId, ['running', 'pause_requested']);
  await actOnRenderJob(request, projectId, running, 'pause');
  await waitForRenderStatus(request, projectId, ['paused']);
  await page.reload();
  const taskCenter = page.getByLabel('后台任务中心');
  await expect(taskCenter.getByRole('button', { name: '继续' })).toBeVisible();
  await taskCenter.getByRole('button', { name: '继续' }).click();
  await waitForRenderStatus(request, projectId, ['queued', 'running', 'pause_requested']);
}

async function actOnRenderJob(
  request: APIRequestContext,
  projectId: string,
  job: CurrentRenderJob,
  action: 'pause' | 'resume' | 'cancel',
): Promise<void> {
  let current = job;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await request.post(
      `${apiBaseUrl}/api/projects/${projectId}/video/render-jobs/${current.id}/actions`,
      { data: { action, expected_revision: current.revision } },
    );
    if (response.ok()) return;
    if (response.status() !== 409 || attempt === 1) {
      throw new Error(
        `render ${action} was rejected (${response.status()}): ${await response.text()}`,
      );
    }
    current = await currentRenderJob(request, projectId);
  }
}

async function waitForCompletedRenderJob(
  request: APIRequestContext,
  projectId: string,
): Promise<void> {
  await waitForRenderStatus(request, projectId, ['succeeded']);
}

async function waitForRenderStatus(
  request: APIRequestContext,
  projectId: string,
  statuses: string[],
): Promise<CurrentRenderJob> {
  let observed: CurrentRenderJob | null = null;
  await expect
    .poll(
      async () => {
        try {
          observed = await currentRenderJob(request, projectId);
          return statuses.includes(observed.status);
        } catch {
          return false;
        }
      },
      { timeout: 120_000, intervals: [250, 500, 1_000] },
    )
    .toBe(true);
  return observed!;
}

function projectIdFrom(url: string): string {
  const projectId = new URL(url).pathname.split('/')[2];
  if (!projectId) throw new Error(`project id missing from URL: ${url}`);
  return projectId;
}

function installFailureEvidence(page: Page, testInfo: TestInfo, profile: FixtureProfile) {
  const consoleErrors: string[] = [];
  const networkFailures: Array<{ method: string; url: string; error: string }> = [];
  const context = {
    candidate: process.env.PROGRAM_CANDIDATE_ID ?? 'workspace',
    run: process.env.PROGRAM_RUN_ID ?? testInfo.workerIndex.toString(),
    scenario: `DG2-${profile}-local-audio`,
  };
  testInfo.annotations.push({ type: 'dg2-context', description: JSON.stringify(context) });
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('requestfailed', (request) => {
    networkFailures.push({
      method: request.method(),
      url: request.url(),
      error: request.failure()?.errorText ?? 'unknown request failure',
    });
  });
  return {
    flush: async () => {
      const unexpectedNetworkFailures = networkFailures.filter(
        (failure) => failure.error !== 'net::ERR_ABORTED',
      );
      const evidencePath = testInfo.outputPath('dg2-browser-context.json');
      await writeFile(
        evidencePath,
        JSON.stringify({ ...context, consoleErrors, networkFailures, unexpectedNetworkFailures }, null, 2),
        'utf8',
      );
      await testInfo.attach('dg2-browser-context.json', {
        path: evidencePath,
        contentType: 'application/json',
      });
      expect(unexpectedNetworkFailures).toEqual([]);
    },
  };
}

async function attachSuccessfulBrowserEvidence(
  page: Page,
  testInfo: TestInfo,
  profile: FixtureProfile,
  projectId: string,
  jobId: string,
): Promise<void> {
  const screenshot = await page.screenshot({ fullPage: true });
  await testInfo.attach(`dg2-${profile.toLowerCase()}-completed.png`, {
    body: screenshot,
    contentType: 'image/png',
  });
  await testInfo.attach(`dg2-${profile.toLowerCase()}-completed.json`, {
    body: Buffer.from(JSON.stringify({ projectId, jobId, status: 'succeeded' }, null, 2)),
    contentType: 'application/json',
  });
}
