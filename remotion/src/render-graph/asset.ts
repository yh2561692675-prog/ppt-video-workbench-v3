import { staticFile } from 'remotion';

export function graphAssetSource(path: string, assetBaseUrl = ''): string {
  if (path.startsWith('http://') || path.startsWith('https://') || path.startsWith('/'))
    return path;
  const joined = assetBaseUrl ? `${assetBaseUrl.replace(/\/$/, '')}/${path}` : path;
  return staticFile(joined.replace(/^\/+/, ''));
}

export function mediaKind(
  kind: string,
  sourceRef: string,
): 'image' | 'video' | 'audio' | 'unknown' {
  if (kind === 'video' || /\.(mp4|webm|mov|m4v)$/i.test(sourceRef)) return 'video';
  if (kind === 'audio' || /\.(wav|mp3|m4a|aac|ogg)$/i.test(sourceRef)) return 'audio';
  if (kind === 'image' || /\.(png|jpe?g|gif|svg|webp)$/i.test(sourceRef)) return 'image';
  return 'unknown';
}
