export type EffectFeatureFlags = {
  persistence: boolean;
  preview: boolean;
  render: boolean;
};

export function effectFeatureFlags(env: Record<string, string | undefined>): EffectFeatureFlags {
  const read = (key: string) => ['1', 'true', 'yes', 'on'].includes((env[key] ?? '').toLowerCase());
  const flags = {
    persistence: read('VITE_EFFECT_V2_PERSISTENCE'),
    preview: read('VITE_EFFECT_V2_PREVIEW'),
    render: read('VITE_EFFECT_V2_RENDER'),
  };
  if ((flags.preview || flags.render) && !flags.persistence) {
    throw new Error('Effect Engine V2 preview/render requires persistence');
  }
  return flags;
}
