import { CalculateMetadataFunction, Composition } from 'remotion';

import { ProjectVideo } from './video/ProjectVideo';
import type { ProjectVideoProps } from './video/types';
import { RenderGraphComposition } from './render-graph/RenderGraphComposition';
import type { RenderGraphProps } from './render-graph/types';
import { durationToFrames } from './render-graph/types';

const defaultProps: ProjectVideoProps = {
  schema_version: 1,
  project_id: '00000000-0000-0000-0000-000000000001',
  width: 1920,
  height: 1080,
  fps: 30,
  duration_ms: 1000,
  template_version: 'tech-board-v1',
  reduced_motion: false,
  pages: [
    {
      page_id: '00000000-0000-0000-0000-000000000002',
      page_order: 1,
      title: '预览',
      image_path: '',
      audio_path: '',
      start_ms: 0,
      end_ms: 1000,
      subtitle_cue_ids: [],
    },
  ],
  subtitles: [],
  subtitle_placements: [],
};

const calculateMetadata: CalculateMetadataFunction<{ props: ProjectVideoProps }> = ({ props }) => ({
  durationInFrames: Math.max(
    1,
    Math.floor((props.props.duration_ms * props.props.fps + 500) / 1000),
  ),
  fps: props.props.fps,
  width: props.props.width,
  height: props.props.height,
});

const defaultGraphProps: RenderGraphProps = {
  graph: {
    schema_version: '2.0',
    graph_id: '00000000-0000-4000-8000-000000000003',
    project_id: '00000000-0000-0000-0000-000000000001',
    timeline_revision: 1,
    timeline_hash: '0000000000000000000000000000000000000000000000000000000000000000',
    compiler_version: 'rendergraph-v2-default',
    duration_us: 1_000_000,
    canvas: {
      width: 1920,
      height: 1080,
      fps: 30,
      fps_num: 30,
      fps_den: 1,
      duration_us: 1_000_000,
      background: '#000000',
      pixel_format: 'yuv420p',
      aspect_ratio: '16:9',
    },
    nodes: [],
    transitions: [],
    assets: [],
    audio: { clips: [], ducking: [], loudness_target_lufs: -16, true_peak_db: -1 },
    subtitles: {
      render_mode: 'none',
      cues: [],
      default_style: {},
      languages: [],
      document_revision: 1,
      document_hash: '0000000000000000000000000000000000000000000000000000000000000000',
      tracks: [],
    },
    source_revisions: {},
    affected_ranges: [],
    graph_hash: '0000000000000000000000000000000000000000000000000000000000000000',
  },
  executionMode: 'interactive-preview',
};

const calculateGraphMetadata: CalculateMetadataFunction<RenderGraphProps> = ({ props }) => ({
  durationInFrames: durationToFrames(props.graph.duration_us, props.graph.canvas.fps),
  fps: props.graph.canvas.fps,
  width: props.graph.canvas.width,
  height: props.graph.canvas.height,
});

export const RemotionRoot = () => (
  <>
    <Composition
      id="PptVideoWorkbench"
      component={ProjectVideo}
      defaultProps={{ props: defaultProps }}
      durationInFrames={30}
      fps={30}
      width={1920}
      height={1080}
      calculateMetadata={calculateMetadata}
    />
    <Composition
      id="RenderGraphV2"
      component={RenderGraphComposition}
      defaultProps={defaultGraphProps}
      durationInFrames={30}
      fps={30}
      width={1920}
      height={1080}
      calculateMetadata={calculateGraphMetadata}
    />
  </>
);
