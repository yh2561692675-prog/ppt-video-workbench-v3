import { expect, it } from 'vitest';

import durableJobFixture from '../../../../tests/fixtures/durable-job-v1.json';

import type { DurableJobDetail } from './client';

it('consumes the durable Job golden fixture exposed by the Python contract', () => {
  const detail = durableJobFixture as unknown as DurableJobDetail;

  expect(detail.job.job_type).toBe('render_preview');
  expect(detail.job.current_attempt_id).toBe(detail.attempts[0].id);
  expect(detail.attempts[0].generation).toBe(1);
  expect(detail.latest_checkpoint?.attempt_id).toBe(detail.attempts[0].id);
  expect(detail.latest_checkpoint?.sequence).toBe(detail.attempts[0].checkpoint_sequence);
});
