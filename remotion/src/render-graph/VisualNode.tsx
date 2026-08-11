import { AbsoluteFill, Img, Video, useCurrentFrame } from 'remotion';

import { graphAssetSource, mediaKind } from './asset';
import { transitionOpacity, transitionStyle } from './transition';
import type { RenderGraphV2, RenderNodeV2 } from './types';

export function VisualNode({
  graph,
  node,
  assetBaseUrl = '',
}: {
  graph: RenderGraphV2;
  node: RenderNodeV2;
  assetBaseUrl?: string;
}) {
  const frame = useCurrentFrame();
  const source =
    graph.assets.find((asset) => asset.source_ref === node.source_ref)?.resolved_path ??
    node.source_ref;
  const kind = mediaKind(node.kind, source);
  const style = transitionStyle(graph, node, frame);
  const opacity = transitionOpacity(graph, node, frame);
  const payload = node.payload;
  const fit = payload.crop === 'cover' ? 'cover' : payload.crop === 'fill' ? 'fill' : 'contain';
  const mediaStyle: React.CSSProperties = {
    width: '100%',
    height: '100%',
    objectFit: fit,
    display: 'block',
  };
  const content =
    kind === 'video' ? (
      <Video
        src={graphAssetSource(source, assetBaseUrl)}
        startFrom={Math.max(0, Math.floor((node.source_in_us * graph.canvas.fps) / 1_000_000))}
        muted
        style={mediaStyle}
      />
    ) : kind === 'image' ? (
      <Img src={graphAssetSource(source, assetBaseUrl)} style={mediaStyle} />
    ) : null;
  if (!content) return null;
  return (
    <AbsoluteFill
      style={{
        zIndex: node.z_index,
        opacity,
        mixBlendMode: node.blend_mode as React.CSSProperties['mixBlendMode'],
        pointerEvents: 'none',
        ...style,
      }}
    >
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        {content}
      </div>
    </AbsoluteFill>
  );
}
