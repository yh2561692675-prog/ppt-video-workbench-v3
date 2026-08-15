import path from 'node:path';

import { defineConfig } from '@playwright/test';

const collectCiEvidence = Boolean(process.env.CI || process.env.PLAYWRIGHT_CI_EVIDENCE);
// The Windows console launcher leaves media-worker child handles open after
// a successful run.  Local Windows acceptance therefore defaults to explicitly
// managed services; CI retains Playwright-owned isolated servers.
const useExternalServers =
  process.env.PLAYWRIGHT_EXTERNAL_SERVERS === '1' ||
  (process.platform === 'win32' && !process.env.CI);
// Every browser run gets an isolated workspace.  A cancelled Windows run can
// leave a daemon render worker alive for a short time; sharing the fixed
// workspace would let that worker claim jobs from the next run.
const e2eWorkspace = path.resolve('test-results', `e2e-workspace-${process.pid}`);
// Local Windows acceptance must exercise the bundled runtime layout. CI
// installs its own Node/FFmpeg toolchain on each runner and does not check in
// the machine-specific runtime-assets directory, so leave this unset there.
const runtimeRoot =
  process.env.WORKBENCH_RUNTIME_ROOT ??
  (!process.env.CI && process.platform === 'win32' ? path.resolve('runtime-assets') : undefined);
const servicePath =
  process.platform === 'win32'
    ? [`C:\\Program Files\\LibreOffice\\program`, process.env.PATH]
        .filter((value): value is string => Boolean(value))
        .join(path.delimiter)
    : process.env.PATH;

export default defineConfig({
  testDir: './tests/e2e',
  globalSetup: './tests/e2e/global-setup.ts',
  outputDir: 'test-results/playwright',
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
    channel: process.platform === 'win32' ? 'msedge' : undefined,
    // Acceptance evidence must also be reviewable after a successful browser
    // run.  Normal developer feedback stays compact; CI/evidence mode retains
    // the full trace, video and screenshot set.
    trace: collectCiEvidence ? 'on' : 'retain-on-failure',
    screenshot: collectCiEvidence ? 'on' : 'only-on-failure',
    video: collectCiEvidence ? 'on' : 'retain-on-failure',
  },
  // Windows may retain a child process handle after a media-rendering run.
  // DG2 can therefore exercise the identical browser suite against explicitly
  // managed services, while CI keeps the normal owned-server lifecycle.
  webServer: useExternalServers
    ? undefined
    : [
        {
          command:
            process.platform === 'win32'
              ? // Invoke Python directly: the `uvicorn.exe` console wrapper creates
                // a child process that Playwright cannot reliably close on Windows.
                '.\\.venv\\Scripts\\python.exe -m uvicorn workbench.main:app --host 127.0.0.1 --port 8765 --log-level warning'
              : 'uv run uvicorn workbench.main:app --host 127.0.0.1 --port 8765',
          cwd: '.',
          env: {
            ...process.env,
            // The acceptance API must import the checked-out source, rather than
            // any editable package previously installed into the shared venv.
            PYTHONPATH: path.resolve('apps/api/src'),
            // Keep the Windows Uvicorn launcher and its child-process readers on
            // UTF-8, including when the browser flow emits Chinese fixture data.
            PYTHONUTF8: '1',
            PYTHONIOENCODING: 'utf-8',
            // CI installs LibreOffice globally. Chocolatey's program directory
            // is not propagated to later Windows steps, so pass it explicitly
            // to the API process that renders PPTX previews.
            PATH: servicePath,
            // Exercise the same self-contained renderer layout required by the
            // Windows launcher; never fall back to a global pnpm/Remotion tool.
            WORKBENCH_WORKSPACE: e2eWorkspace,
            ...(runtimeRoot ? { WORKBENCH_RUNTIME_ROOT: runtimeRoot } : {}),
            WORKBENCH_E2E_SYNTHETIC_MODE: 'true',
            WORKBENCH_DG2_RENDER_DELAY_SECONDS: process.env.DG2_RENDER_DELAY_SECONDS ?? '1',
            UV_CACHE_DIR: process.env.UV_CACHE_DIR ?? '/tmp/ppt-video-workbench-uv-cache',
          },
          url: 'http://127.0.0.1:8765/api/health',
          reuseExistingServer: !process.env.CI,
        },
        {
          command:
            process.platform === 'win32'
              ? 'node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173'
              : 'pnpm --filter @workbench/web exec vite --host 127.0.0.1 --port 4173',
          cwd: 'apps/web',
          url: 'http://127.0.0.1:4173',
          reuseExistingServer: !process.env.CI,
        },
      ],
});
