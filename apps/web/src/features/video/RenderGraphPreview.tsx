import { Player, PlayerRef } from '@remotion/player';
import { useRef } from 'react';

import { RenderGraphComposition } from '../../../../../remotion/src/render-graph/RenderGraphComposition';
import {
  durationToFrames,
  type RenderGraphV2,
} from '../../../../../remotion/src/render-graph/types';

interface RenderGraphPreviewProps {
  projectId: string;
  graph: RenderGraphV2;
}

export function RenderGraphPreview({ projectId, graph }: RenderGraphPreviewProps) {
  const playerRef = useRef<PlayerRef>(null);
  const assetBaseUrl = `/api/projects/${projectId}/video/assets`;
  return (
    <section className="render-graph-preview" aria-label="RenderGraph V2 预览">
      <div className="preview-plan-meta">
        RenderGraph V2 · revision {graph.timeline_revision} · hash{' '}
        {graph.graph_hash ?? graph.content_hash}
      </div>
      <Player
        ref={playerRef}
        component={RenderGraphComposition}
        inputProps={{ graph, executionMode: 'interactive-preview', assetBaseUrl }}
        durationInFrames={durationToFrames(graph.duration_us, graph.canvas.fps)}
        compositionWidth={graph.canvas.width}
        compositionHeight={graph.canvas.height}
        fps={graph.canvas.fps}
        controls
        acknowledgeRemotionLicense
        style={{ width: '100%', aspectRatio: `${graph.canvas.width} / ${graph.canvas.height}` }}
      />
    </section>
  );
}
