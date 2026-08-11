import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ProviderSettingsPanel } from './ProviderSettingsPanel';

describe('ProviderSettingsPanel', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('shows reviewed providers and credential metadata without secrets', async () => {
    vi.stubGlobal('fetch', async (input: RequestInfo | URL) => {
      const url = String(input);
      const body = url.endsWith('/credentials')
        ? [{
            credential_ref: 'llm.main',
            provider_id: 'builtin-llm',
            scope: 'tenant:test',
            status: 'active',
            created_at: '2026-08-11T00:00:00Z',
            updated_at: '2026-08-11T00:00:00Z',
          }]
        : [{
            provider_id: 'builtin-llm',
            display_name: 'Built-in LLM seam',
            kind: 'llm',
            adapter_version: '1.0.0',
            execution_mode: 'in_process_builtin',
            capabilities: [{
              capability_id: 'completion',
              modalities: ['llm'],
              supports_cancellation: true,
              supports_cost_estimate: true,
            }],
            enabled: true,
            trust: 'builtin_signed',
          }];
      return new Response(JSON.stringify(body), {
        headers: { 'Content-Type': 'application/json' },
      });
    });

    render(
      <QueryClientProvider client={new QueryClient()}>
        <ProviderSettingsPanel />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Built-in LLM seam')).toBeInTheDocument();
    expect(await screen.findByText('llm.main')).toBeInTheDocument();
    expect(screen.queryByText('top-secret')).not.toBeInTheDocument();
  });
});
