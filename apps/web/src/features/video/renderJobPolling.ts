import type { RenderJob } from '../../api/client';

export function renderJobPollInterval(job: RenderJob | null | undefined): number | false {
  if (!job || ['succeeded', 'failed', 'cancelled'].includes(job.status)) return false;
  if (job.status === 'paused') return 5000;
  return 1000;
}
