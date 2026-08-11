export type CacheDomain =
  | 'video_only'
  | 'audio'
  | 'subtitle_soft'
  | 'subtitle_burn_in'
  | 'transition'
  | 'overlay'
  | 'layout'
  | 'final';

export interface CacheArtifactRef {
  relative_path: string;
  sha256: string;
  size_bytes: number;
}

export interface CacheDependencyV1 {
  schema_version: '1.0';
  domain: CacheDomain;
  node_key: string;
  upstream_kind: string;
  upstream_key: string;
  upstream_hash: string;
  start_us: number | null;
  end_us: number | null;
  artifact_refs: CacheArtifactRef[];
}

export type CacheStaleReason =
  | 'source_revision_changed'
  | 'asset_revision_changed'
  | 'runtime_incompatible'
  | 'license_invalid'
  | 'artifact_mismatch'
  | 'layout_changed';
