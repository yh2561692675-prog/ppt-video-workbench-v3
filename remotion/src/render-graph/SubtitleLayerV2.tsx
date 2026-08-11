import { AbsoluteFill, useCurrentFrame } from 'remotion';

import type { RenderGraphV2, SubtitleCue } from './types';

export function SubtitleLayerV2({ graph }: { graph: RenderGraphV2 }) {
  const frame = useCurrentFrame();
  if (graph.subtitles.render_mode !== 'burn_in' && graph.subtitles.render_mode !== 'both')
    return null;
  const timeUs = Math.floor((frame * 1_000_000) / graph.canvas.fps);
  const active = graph.subtitles.cues.filter(
    (cue) => cue.start_us <= timeUs && timeUs < cue.end_us,
  );
  if (!active.length) return null;
  const primary = active.find((cue) => cue.language === graph.subtitles.languages[0]) ?? active[0];
  const secondary = active.find((cue) => cue.language !== primary.language);
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        zIndex: 900,
        alignItems: 'center',
        justifyContent: 'flex-end',
        padding: '0 8% 7%',
      }}
    >
      <div style={styleForCue(graph, primary)}>
        <HighlightedText
          cue={primary}
          timeUs={timeUs}
          color={String(primary.style.color ?? '#FFFFFF')}
          highlightColor={String(primary.style.highlight_color ?? '#FFD54F')}
        />
        {secondary ? (
          <div style={{ marginTop: 8, fontSize: '72%', opacity: 0.9 }}>
            <HighlightedText
              cue={secondary}
              timeUs={timeUs}
              color={String(secondary.style.color ?? '#FFFFFF')}
              highlightColor={String(secondary.style.highlight_color ?? '#FFD54F')}
            />
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
}

function styleForCue(graph: RenderGraphV2, cue: SubtitleCue): React.CSSProperties {
  const style = { ...graph.subtitles.default_style, ...cue.style };
  const fontSize =
    typeof style.font_size === 'number' ? style.font_size : Math.max(22, graph.canvas.width / 64);
  const outline = typeof style.outline_width === 'number' ? style.outline_width : 2;
  return {
    maxWidth: '88%',
    padding: '14px 24px',
    borderRadius: 12,
    color: String(style.color ?? '#FFFFFF'),
    background: `${String(style.background_color ?? '#000000')}${Math.round(
      Number(style.background_opacity ?? 0.55) * 255,
    )
      .toString(16)
      .padStart(2, '0')}`,
    fontFamily: String(style.font_family ?? 'sans-serif'),
    fontSize,
    lineHeight: 1.35,
    textAlign: 'center',
    WebkitTextStroke: `${outline}px ${String(style.outline_color ?? '#000000')}`,
    whiteSpace: 'pre-wrap',
  };
}

function HighlightedText({
  cue,
  timeUs,
  color,
  highlightColor,
}: {
  cue: SubtitleCue;
  timeUs: number;
  color: string;
  highlightColor: string;
}) {
  if (!cue.words.length) return <span style={{ color }}>{cue.text}</span>;
  return (
    <span>
      {cue.words.map((word, index) => (
        <span
          key={`${cue.id}-${index}`}
          style={{
            color: word.start_us <= timeUs && timeUs < word.end_us ? highlightColor : color,
          }}
        >
          {word.text}
          {index < cue.words.length - 1 ? ' ' : ''}
        </span>
      ))}
    </span>
  );
}
