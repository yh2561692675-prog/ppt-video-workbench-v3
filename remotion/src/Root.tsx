import { CalculateMetadataFunction, Composition } from 'remotion';

import { ProjectVideo } from './video/ProjectVideo';
import type { ProjectVideoProps } from './video/types';

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

export const RemotionRoot = () => (
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
);
