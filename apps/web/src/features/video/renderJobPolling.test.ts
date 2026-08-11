import { expect, it } from 'vitest';

import { renderJobPollInterval } from './renderJobPolling';

it('polls active jobs every second and paused jobs every five seconds', () => {
  expect(renderJobPollInterval({ status: 'running' } as never)).toBe(1000);
  expect(renderJobPollInterval({ status: 'paused' } as never)).toBe(5000);
  expect(renderJobPollInterval({ status: 'succeeded' } as never)).toBe(false);
  expect(renderJobPollInterval(null)).toBe(false);
});
