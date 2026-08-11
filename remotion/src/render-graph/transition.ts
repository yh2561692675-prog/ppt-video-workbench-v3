import { interpolate } from 'remotion';

import type { RenderNodeV2, RenderGraphV2, TransitionEdge } from './types';
import { usToFrames } from './types';

export function activeTransition(
  graph: RenderGraphV2,
  node: RenderNodeV2,
  frame: number,
): TransitionEdge | undefined {
  return graph.transitions.find((edge) => {
    const start = usToFrames(edge.start_us, graph.canvas.fps);
    const end = Math.max(start + 1, usToFrames(edge.end_us, graph.canvas.fps));
    return (
      (edge.from_node_id === node.id || edge.to_node_id === node.id) &&
      frame >= start &&
      frame < end
    );
  });
}

export function transitionOpacity(graph: RenderGraphV2, node: RenderNodeV2, frame: number): number {
  const edge = activeTransition(graph, node, frame);
  if (!edge || edge.kind === 'cut' || edge.end_us <= edge.start_us) return node.opacity;
  const start = usToFrames(edge.start_us, graph.canvas.fps);
  const end = Math.max(start + 1, usToFrames(edge.end_us, graph.canvas.fps));
  const progress = interpolate(frame, [start, end], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const eased =
    edge.easing === 'ease_in'
      ? progress * progress
      : edge.easing === 'ease_out'
        ? 1 - (1 - progress) ** 2
        : edge.easing === 'ease_in_out'
          ? progress < 0.5
            ? 2 * progress ** 2
            : 1 - (-2 * progress + 2) ** 2 / 2
          : progress;
  return node.id === edge.to_node_id ? node.opacity * eased : node.opacity * (1 - eased);
}

export function transitionStyle(
  graph: RenderGraphV2,
  node: RenderNodeV2,
  frame: number,
): React.CSSProperties {
  const edge = activeTransition(graph, node, frame);
  if (!edge || edge.kind === 'cut') return {};
  const start = usToFrames(edge.start_us, graph.canvas.fps);
  const end = Math.max(start + 1, usToFrames(edge.end_us, graph.canvas.fps));
  const progress = interpolate(frame, [start, end], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  if (edge.kind === 'wipe')
    return {
      clipPath: `inset(0 ${node.id === edge.to_node_id ? (1 - progress) * 100 : progress * 100}% 0 0)`,
    };
  if (edge.kind === 'slide')
    return {
      transform: `translateX(${node.id === edge.to_node_id ? (1 - progress) * 100 : -progress * 100}%)`,
    };
  return {};
}
