import { AbsoluteFill, Audio, Sequence } from 'remotion';

import { graphAssetSource } from './asset';
import { OverlayLayer } from './OverlayLayer';
import { SubtitleLayerV2 } from './SubtitleLayerV2';
import { durationToFrames, type RenderGraphProps, usToFrames } from './types';
import { VisualNode } from './VisualNode';

export function RenderGraphComposition({ graph, assetBaseUrl = '' }: RenderGraphProps) {
  const visualNodes = graph.nodes.filter(
    (node) => !['narration', 'presenter', 'music', 'sfx', 'subtitle'].includes(node.kind),
  );
  return (
    <AbsoluteFill style={{ backgroundColor: graph.canvas.background, overflow: 'hidden' }}>
      {visualNodes.map((node) => (
        <Sequence
          key={node.id}
          from={usToFrames(node.start_us, graph.canvas.fps)}
          durationInFrames={durationToFrames(node.end_us - node.start_us, graph.canvas.fps)}
          premountFor={graph.canvas.fps}
        >
          {node.kind === 'overlay' ? (
            <OverlayLayer graph={graph} node={node} assetBaseUrl={assetBaseUrl} />
          ) : (
            <VisualNode graph={graph} node={node} assetBaseUrl={assetBaseUrl} />
          )}
        </Sequence>
      ))}
      {graph.audio.clips.map((clip) => (
        <Sequence
          key={`audio-${clip.id}`}
          from={usToFrames(clip.timeline_start_us, graph.canvas.fps)}
          durationInFrames={durationToFrames(
            clip.timeline_end_us - clip.timeline_start_us,
            graph.canvas.fps,
          )}
        >
          <Audio
            src={graphAssetSource(resolveAssetPath(graph, clip.source_ref), assetBaseUrl)}
            startFrom={usToFrames(clip.source_in_us, graph.canvas.fps)}
            volume={10 ** (clip.gain_db / 20)}
          />
        </Sequence>
      ))}
      <SubtitleLayerV2 graph={graph} />
    </AbsoluteFill>
  );
}

function resolveAssetPath(graph: RenderGraphProps['graph'], sourceRef: string): string {
  return graph.assets.find((asset) => asset.source_ref === sourceRef)?.resolved_path ?? sourceRef;
}
