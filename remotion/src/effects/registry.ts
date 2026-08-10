import type { ComponentType } from 'react';

import type { EffectPlanV2, EffectTemplateName } from '../types';

export type EffectTemplateProps = { plan: EffectPlanV2; currentFrame: number };
export type EffectTemplateComponent = ComponentType<EffectTemplateProps>;

export type EffectTemplateDescriptor = {
  name: EffectTemplateName;
  component: EffectTemplateComponent;
  supportedAspectRatios: readonly ['16:9', '9:16'];
  performance: 'safe' | 'standard';
  fallback: EffectTemplateName;
};

const descriptors = new Map<EffectTemplateName, EffectTemplateDescriptor>();

export function registerEffect(
  name: EffectTemplateName,
  component: EffectTemplateComponent,
  metadata: Partial<Omit<EffectTemplateDescriptor, 'name' | 'component'>> = {
    supportedAspectRatios: ['16:9', '9:16'],
    performance: 'standard',
    fallback: 'SafeSlide',
  },
): void {
  descriptors.set(name, {
    name,
    component,
    supportedAspectRatios: ['16:9', '9:16'],
    performance: 'standard',
    fallback: 'SafeSlide',
    ...metadata,
  });
}

export function getEffect(name: string): EffectTemplateDescriptor | undefined {
  return descriptors.get(name as EffectTemplateName);
}

export function listEffects(): readonly EffectTemplateDescriptor[] {
  return [...descriptors.values()];
}
