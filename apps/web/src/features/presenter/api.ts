import type { Project } from '../../api/client';

export type PresenterSource = {
  id: string;
  relative_path: string;
  sha256: string;
  duration_ms: number;
  media_type: 'video/mp4' | 'video/quicktime';
  probe_snapshot: Record<string, unknown>;
  imported_at: string | null;
};

export type PresenterAnchor = {
  page_id: string;
  start_ms: number;
  end_ms: number;
  sentence_ids: string[];
  confidence: number;
  status: 'auto' | 'review' | 'blocked' | 'confirmed';
  manual_lock: boolean;
  source_revision: string | null;
};

export type PresenterSegment = {
  start_ms: number;
  end_ms: number;
  layout: 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right' | 'center' | 'split' | 'hidden';
  width_ratio: number;
  manual_lock: boolean;
  source_revision: string | null;
};

export type PresenterTimeline = {
  schema_version: '1.0';
  revision: number;
  source_id: string;
  source_version: string;
  duration_ms: number;
  anchors: PresenterAnchor[];
  segments: PresenterSegment[];
  unassigned_ranges: Array<{ start_ms: number; end_ms: number; reason: string }>;
  timeline_hash: string | null;
  generated_at: string | null;
};

export type PresenterAnalysisResponse = {
  project: Project;
  transcript: { content_hash: string; sentences: Array<{ id: string; text: string }> };
  matches: {
    matches: Array<{ page_id: string; score: number }>;
    unassigned_sentence_ids: string[];
  };
};

type Envelope<T> = {
  data: T;
  error: null | {
    code: string;
    message: string;
    action?: string;
    current_revision?: number | null;
    timeline_hash?: string | null;
  };
};

export class PresenterApiError extends Error {
  constructor(
    readonly code: string,
    message: string,
    readonly status: number,
    readonly currentRevision: number | null = null,
    readonly timelineHash: string | null = null,
  ) {
    super(message);
    this.name = 'PresenterApiError';
  }
}

async function presenterRequest<T>(path: string, init: RequestInit): Promise<T> {
  const isFormData = init.body instanceof FormData;
  const response = await fetch(path, {
    ...init,
    headers: isFormData ? init.headers : { 'Content-Type': 'application/json', ...init.headers },
  });
  const body = (await response.json()) as Envelope<T>;
  if (!response.ok || body.error) {
    throw new PresenterApiError(
      body.error?.code ?? 'presenter_request_failed',
      body.error?.message ?? `HTTP ${response.status}`,
      response.status,
      body.error?.current_revision ?? null,
      body.error?.timeline_hash ?? null,
    );
  }
  return body.data;
}

export const presenterApi = {
  importSource(projectId: string, file: File): Promise<Project> {
    const form = new FormData();
    form.append('file', file);
    return presenterRequest(`/api/projects/${projectId}/presenter-source`, {
      method: 'POST',
      body: form,
    });
  },
  analyze(projectId: string): Promise<PresenterAnalysisResponse> {
    return presenterRequest(`/api/projects/${projectId}/presenter-analysis`, { method: 'POST' });
  },
  patchAnchor(
    projectId: string,
    pageId: string,
    input: {
      expected_revision: number;
      start_ms: number;
      end_ms: number;
      sentence_ids?: string[];
      confidence?: number;
      manual_lock?: boolean;
    },
  ): Promise<Project> {
    return presenterRequest(`/api/projects/${projectId}/presenter-timeline/anchors/${pageId}`, {
      method: 'PATCH',
      body: JSON.stringify(input),
    });
  },
};
