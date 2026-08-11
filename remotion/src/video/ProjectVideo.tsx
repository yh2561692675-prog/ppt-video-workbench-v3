import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame } from 'remotion';

import { PresenterLayer } from '../presenter/PresenterLayer';
import { PageScene } from './PageScene';
import type { ProjectVideoProps, VideoPageProps } from './types';
import { msToFrames } from './types';

export function ProjectVideo({ props }: { props: ProjectVideoProps }) {
  const fps = props.fps;
  return (
    <AbsoluteFill>
      {props.pages.map((page) => (
        <Sequence
          key={page.page_id}
          from={msToFrames(page.start_ms, fps)}
          durationInFrames={msToFrames(page.end_ms - page.start_ms, fps)}
          premountFor={fps}
        >
          <PageAtLocalFrame page={page} props={props} />
        </Sequence>
      ))}
      {props.presenter_timeline && props.presenter_source_path ? (
        <>
          <PresenterLayer
            source={props.presenter_source_path}
            timeline={props.presenter_timeline}
            fps={fps}
            width={props.width}
            height={props.height}
            reducedMotion={props.reduced_motion}
          />
          <Audio src={assetSource(props.presenter_source_path)} />
        </>
      ) : (
        props.pages.map((item) => (
          <Sequence
            key={`${item.page_id}-audio`}
            from={msToFrames(item.start_ms, fps)}
            durationInFrames={msToFrames(item.end_ms - item.start_ms, fps)}
            premountFor={fps}
          >
            <Audio src={assetSource(item.audio_path)} />
          </Sequence>
        ))
      )}
    </AbsoluteFill>
  );
}

function PageAtLocalFrame({ page, props }: { page: VideoPageProps; props: ProjectVideoProps }) {
  const localFrame = useCurrentFrame();
  const placement = props.subtitle_placements.find((item) => item.page_id === page.page_id);
  return <PageScene page={page} props={props} localFrame={localFrame} placement={placement} />;
}

function assetSource(path: string): string {
  return path.startsWith('/') ? path : staticFile(path);
}
