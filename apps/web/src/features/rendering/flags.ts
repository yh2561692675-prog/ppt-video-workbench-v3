export type RendererGeneration = 'v1' | 'v2';

export type RenderFeatureFlags = {
  compile: boolean;
  preview: boolean;
  export: boolean;
  strictAssets: boolean;
  rendererGeneration: RendererGeneration;
};

const enabled = (value: string | undefined): boolean =>
  ['1', 'true', 'yes', 'on'].includes((value ?? '').trim().toLowerCase());

const generation = (value: string | undefined): RendererGeneration => {
  const normalized = (value ?? 'v1').trim().toLowerCase();
  if (normalized !== 'v1' && normalized !== 'v2') {
    throw new Error("renderer generation must be 'v1' or 'v2'");
  }
  return normalized;
};

export function renderFeatureFlags(
  env: Record<string, string | undefined> = {},
): RenderFeatureFlags {
  return {
    compile: enabled(env.WORKBENCH_RENDERGRAPH_V2_COMPILE ?? env.VITE_RENDERGRAPH_V2_COMPILE),
    preview: enabled(env.WORKBENCH_RENDERGRAPH_V2_PREVIEW ?? env.VITE_RENDERGRAPH_V2_PREVIEW),
    export: enabled(env.WORKBENCH_RENDERGRAPH_V2_EXPORT ?? env.VITE_RENDERGRAPH_V2_EXPORT),
    strictAssets: enabled(
      env.WORKBENCH_RENDERGRAPH_V2_STRICT_ASSETS ?? env.VITE_RENDERGRAPH_V2_STRICT_ASSETS,
    ),
    rendererGeneration: generation(
      env.WORKBENCH_RENDERER_GENERATION ?? env.VITE_RENDERER_GENERATION,
    ),
  };
}

export function forProjectRendererGeneration(
  flags: RenderFeatureFlags,
  rendererGeneration: string | undefined,
): RenderFeatureFlags {
  if (rendererGeneration === undefined) return flags;
  return { ...flags, rendererGeneration: generation(rendererGeneration) };
}

export const renderGraphV2Enabled = (flags: RenderFeatureFlags): boolean =>
  flags.rendererGeneration === 'v2' && flags.compile;

export const renderGraphV2Exclusive = (flags: RenderFeatureFlags): boolean =>
  flags.rendererGeneration === 'v2';
