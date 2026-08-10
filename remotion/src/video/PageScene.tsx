import { AbsoluteFill } from 'remotion';

import { EffectInterpreter } from '../effects/interpreter';
import { TechBoardTemplate } from './TechBoardTemplate';
import type { ProjectVideoProps, SubtitlePlacement, VideoPageProps } from './types';
import { SubtitleLayer } from './SubtitleLayer';

export function PageScene({
  page,
  props,
  localFrame,
  placement,
}: {
  page: VideoPageProps;
  props: ProjectVideoProps;
  localFrame: number;
  placement?: SubtitlePlacement;
}) {
  return (
    <AbsoluteFill>
      <TechBoardTemplate
        page={page}
        subtitles={props.subtitles}
        frame={localFrame + Math.floor((page.start_ms * props.fps) / 1_000)}
        fps={props.fps}
        width={props.width}
        height={props.height}
        reducedMotion={props.reduced_motion}
        placement={placement}
        includeSubtitles={false}
      />
      {page.effect_plan && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 2 }}>
          <EffectInterpreter plan={page.effect_plan} currentFrame={localFrame} />
        </div>
      )}
      <SubtitleLayer
        page={page}
        subtitles={props.subtitles}
        placement={placement}
        frame={localFrame + Math.floor((page.start_ms * props.fps) / 1_000)}
        fps={props.fps}
        width={props.width}
        height={props.height}
      />
    </AbsoluteFill>
  );
}
