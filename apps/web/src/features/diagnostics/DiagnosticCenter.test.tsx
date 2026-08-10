import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';

import { DiagnosticCenter } from './DiagnosticCenter';

afterEach(() => vi.unstubAllGlobals());

it('runs one-click diagnostics, groups failures, and exports a sanitized package', async () => {
  vi.stubGlobal('fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const data = path.endsWith('/package')
      ? {
          report_id: 'report-1',
          relative_path: 'diagnostics/P02-diagnostic-report-1.zip',
          sha256: 'a'.repeat(64),
          size_bytes: 2048,
        }
      : {
          report_id: 'report-1',
          checked_at: '2026-08-09T10:00:00+08:00',
          overall_status: 'red',
          summary: { green: 1, yellow: 0, red: 1 },
          checks: [
            {
              check_id: 'database_integrity',
              label: '数据库完整性',
              status: 'red',
              category: 'STORAGE',
              code: 'DATABASE_INTEGRITY_FAILED',
              summary: '数据库完整性检查未通过',
              impact: '项目状态可能无法读取',
              remediation: '从最近的已验证备份恢复',
              evidence: { database: 'workspace.db' },
            },
            {
              check_id: 'loopback_port',
              label: '本地端口',
              status: 'green',
              category: 'NETWORK',
              code: 'LOOPBACK_PORT_OK',
              summary: '本机回环端口可正常绑定',
              impact: '无影响',
              remediation: '无需处理',
              evidence: {},
            },
          ],
        };
    return new Response(JSON.stringify({ data, error: null, request_id: 'request-1' }), {
      status: init?.method === 'POST' ? 200 : 200,
      headers: { 'Content-Type': 'application/json' },
    });
  });

  render(
    <QueryClientProvider client={new QueryClient()}>
      <BrowserRouter>
        <DiagnosticCenter />
      </BrowserRouter>
    </QueryClientProvider>,
  );

  fireEvent.click(screen.getByRole('button', { name: '开始一键检查' }));

  expect(await screen.findByRole('heading', { name: '需要处理' })).toBeInTheDocument();
  expect(screen.getByText('数据库完整性')).toBeInTheDocument();
  expect(screen.getByText('DATABASE_INTEGRITY_FAILED')).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: '正常' })).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: '生成脱敏诊断包' }));
  expect(await screen.findByText(/P02-diagnostic-report-1\.zip/)).toBeInTheDocument();
});
