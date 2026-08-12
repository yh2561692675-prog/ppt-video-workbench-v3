import path from 'node:path';

import { defineConfig } from '@playwright/test';

const collectCiEvidence = Boolean(process.env.CI || process.env.PLAYWRIGHT_CI_EVIDENCE);

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  fullyParallel: false,
  workers: 1,
  reporter: collectCiEvidence
    ? [
        ['line'],
        ['junit', { outputFile: 'test-results/playwright-junit.xml' }],
        ['html', { outputFolder: 'playwright-report', open: 'never' }],
      ]
    : [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    trace: collectCiEvidence ? 'on' : 'retain-on-failure',
  },
  webServer: [
    {
      command: 'uv run uvicorn workbench.main:app --host 127.0.0.1 --port 8765',
      cwd: '.',
      env: {
        ...process.env,
        WORKBENCH_WORKSPACE: path.resolve('tests/.e2e-workspace'),
        UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? '/tmp/ppt-video-workbench-uv-cache',
      },
      url: 'http://127.0.0.1:8765/api/health',
      reuseExistingServer: !process.env.CI,
    },
    {
      command: 'pnpm --filter @workbench/web exec vite --host 127.0.0.1 --port 4173',
      cwd: '.',
      url: 'http://127.0.0.1:4173',
      reuseExistingServer: !process.env.CI,
    },
  ],
});
