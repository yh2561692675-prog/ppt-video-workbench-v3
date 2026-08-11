import { AbsoluteFill, Img, Video, useCurrentFrame } from 'remotion';

import { graphAssetSource, mediaKind } from './asset';
import type { RenderGraphV2, RenderNodeV2 } from './types';
import { usToFrames } from './types';

export function OverlayLayer({
  graph,
  node,
  assetBaseUrl = '',
}: {
  graph: RenderGraphV2;
  node: RenderNodeV2;
  assetBaseUrl?: string;
}) {
  const frame = useCurrentFrame();
  const local = frame - usToFrames(node.start_us, graph.canvas.fps);
  const total = Math.max(1, usToFrames(node.end_us - node.start_us, graph.canvas.fps));
  const payload = node.payload;
  const x = number(payload.x, 0);
  const y = number(payload.y, 0);
  const width = number(payload.width, 1);
  const height = number(payload.height, 1);
  const enter = Math.max(0, usToFrames(number(payload.enter_ms, 0) * 1000, graph.canvas.fps));
  const exit = Math.max(0, usToFrames(number(payload.exit_ms, 0) * 1000, graph.canvas.fps));
  const opacity =
    enter && local < enter
      ? local / enter
      : exit && local > total - exit
        ? (total - local) / exit
        : 1;
  const source =
    graph.assets.find((asset) => asset.source_ref === node.source_ref)?.resolved_path ??
    node.source_ref;
  const kind = mediaKind(node.kind, source);
  const fit = payload.crop === 'cover' ? 'cover' : payload.crop === 'fill' ? 'fill' : 'contain';
  const mediaStyle: React.CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: fit,
    display: 'block',
  };
  const content =
    kind === 'video' ? (
      <Video src={graphAssetSource(source, assetBaseUrl)} muted style={mediaStyle} />
    ) : kind === 'image' ? (
      <Img src={graphAssetSource(source, assetBaseUrl)} style={mediaStyle} />
    ) : (
      <div>{String(payload.text ?? '')}</div>
    );
  return (
    <AbsoluteFill style={{ zIndex: node.z_index, pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          left: `${x * 100}%`,
          top: `${y * 100}%`,
          width: `${width * 100}%`,
          height: `${height * 100}%`,
          opacity: Math.max(0, Math.min(1, opacity * node.opacity)),
          overflow: 'hidden',
          borderRadius: payload.mask === 'circle' ? '50%' : payload.mask === 'rounded' ? 18 : 0,
        }}
      >
        {content}
      </div>
    </AbsoluteFill>
  );
}

function number(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}
