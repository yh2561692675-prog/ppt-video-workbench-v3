import { registerEffect, getEffect, type EffectTemplateComponent } from './registry';
import { FocusSpotlight } from './templates/FocusSpotlight';
import { ProgressiveReveal } from './templates/ProgressiveReveal';
import { SafeSlide } from './templates/SafeSlide';
import { ChapterCurtain } from './templates/ChapterCurtain';
import { ChartNarration } from './templates/ChartNarration';
import { CompareMode } from './templates/CompareMode';
import { CardStack } from './templates/CardStack';
import { GaugeAndRatio } from './templates/GaugeAndRatio';
import { PathBuilder } from './templates/PathBuilder';
import { TagMatrix } from './templates/TagMatrix';
import { RiskAlert } from './templates/RiskAlert';
import { MapHighlight } from './templates/MapHighlight';
import { StatCounter } from './templates/StatCounter';
import type { EffectPlanV2, EffectTemplateName } from '../types';

/* eslint-disable react-refresh/only-export-components */

const safeProps = (plan: EffectPlanV2, currentFrame: number) => ({ plan, currentFrame });

registerEffect('SafeSlide', SafeSlide, { performance: 'safe', fallback: 'SafeSlide' });
registerEffect('ProgressiveReveal', ProgressiveReveal, { fallback: 'SafeSlide' });
registerEffect('FocusSpotlight', FocusSpotlight, { performance: 'safe', fallback: 'SafeSlide' });
registerEffect(
  'ChapterCurtain',
  ({ plan }) => (
    <ChapterCurtain chapterTitle={plan.page_id} palette="blue" durationMs={plan.duration_ms} />
  ),
  { fallback: 'SafeSlide' },
);
registerEffect(
  'ChartNarration',
  () => <ChartNarration series={[]} cuePoints={[]} annotation="" />,
  { fallback: 'SafeSlide' },
);
registerEffect(
  'CompareMode',
  ({ plan }) => <CompareMode left={plan.page_id} right={plan.page_type} active="left" />,
  { fallback: 'SafeSlide' },
);
registerEffect('CardStack', ({ plan }) => <CardStack cards={[plan.page_id]} />, {
  fallback: 'SafeSlide',
});
registerEffect('GaugeAndRatio', ({ plan }) => <GaugeAndRatio label={plan.page_id} value={0} />, {
  fallback: 'SafeSlide',
});
registerEffect(
  'PathBuilder',
  ({ plan }) => <PathBuilder nodes={[plan.page_id, plan.page_type]} />,
  { fallback: 'SafeSlide' },
);
registerEffect('TagMatrix', ({ plan }) => <TagMatrix tags={[plan.page_id, plan.page_type]} />, {
  fallback: 'SafeSlide',
});
registerEffect(
  'RiskAlert',
  ({ plan }) => <RiskAlert title={plan.page_id} reason={plan.page_type} />,
  { fallback: 'SafeSlide' },
);
registerEffect(
  'MapHighlight',
  ({ plan }) => <MapHighlight points={[]} conclusion={plan.page_type} />,
  { fallback: 'SafeSlide' },
);
registerEffect(
  'StatCounter',
  ({ currentFrame }) => (
    <StatCounter
      spec={{ start: 0, end: 1, durationFrames: 30, format: 'integer' }}
      currentFrame={currentFrame}
    />
  ),
  { fallback: 'SafeSlide' },
);

export type Interpretation = {
  template: EffectTemplateName;
  issueCode: 'EFFECT_TEMPLATE_UNKNOWN' | 'EFFECT_TIMELINE_INVALID' | null;
  component: EffectTemplateComponent;
};

export function interpret(plan: EffectPlanV2, _fps: number): Interpretation {
  void _fps;
  const timelineInvalid = [...plan.cues, ...plan.effects, ...plan.presenter_cues].some(
    (event) =>
      event.start_ms < 0 || event.end_ms <= event.start_ms || event.end_ms > plan.duration_ms,
  );
  if (timelineInvalid) return fallback('EFFECT_TIMELINE_INVALID');

  const requested = plan.template ?? plan.effects[0]?.type ?? 'SafeSlide';
  const descriptor = getEffect(requested);
  if (!descriptor) return fallback('EFFECT_TEMPLATE_UNKNOWN');
  return { template: descriptor.name, issueCode: null, component: descriptor.component };
}

export function EffectInterpreter({
  plan,
  currentFrame,
}: {
  plan: EffectPlanV2;
  currentFrame: number;
}) {
  const result = interpret(plan, 30);
  const Component = result.component;
  return <Component {...safeProps(plan, currentFrame)} />;
}

function fallback(
  issueCode: 'EFFECT_TEMPLATE_UNKNOWN' | 'EFFECT_TIMELINE_INVALID',
): Interpretation {
  const descriptor = getEffect('SafeSlide');
  if (!descriptor) throw new Error('SafeSlide template was not registered');
  return { template: 'SafeSlide', issueCode, component: descriptor.component };
}
