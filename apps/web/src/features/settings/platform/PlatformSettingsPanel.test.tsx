import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PlatformSettingsPanel } from './PlatformSettingsPanel';

describe('PlatformSettingsPanel', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('renders explicit capability states', async () => {
    vi.stubGlobal('fetch', async () =>
      new Response(JSON.stringify({
        schema_version: 1,
        generated_at: '2026-08-11T00:00:00Z',
        flags: { platform_services_enabled: true },
        platform: {
          schema_version: 1,
          info: { platform: 'windows', architecture: 'amd64', runtime_version: 'python-3.12', app_version: '0.1.0' },
          capabilities: ['paths'],
          capability_states: [{ capability_id: 'office.powerpoint_native', status: 'missing', detail: 'PowerPoint runtime is not installed' }],
          tools: [],
          fingerprint: 'sha256:' + 'a'.repeat(64),
          generated_at: '2026-08-11T00:00:00Z',
          expires_at: '2026-08-11T00:15:00Z',
        },
        platform_details: null,
        providers: [],
        sync: null,
      }), { headers: { 'Content-Type': 'application/json' } }),
    );

    render(
      <QueryClientProvider client={new QueryClient()}>
        <PlatformSettingsPanel />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('office.powerpoint_native')).toBeInTheDocument();
    expect(screen.getByText('缺失')).toBeInTheDocument();
  });
});
