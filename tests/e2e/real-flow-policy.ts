export type RealFlowId = 'heygen-two-page' | 'local-audio-windows-rc' | 'presenter-windows-rc';

export interface RealFlowBoundary {
  environment: string;
  reason: string;
  nextGate: 'DG7_OPTIONAL_FEATURES_DECIDED' | 'DG8_V1_DEBUG_ACCEPTED';
  authorization: string;
}

export const REAL_FLOW_BOUNDARIES: Record<RealFlowId, RealFlowBoundary> = {
  'heygen-two-page': {
    environment: 'M8_RUN_REAL_E2E',
    reason: 'requires explicit real HeyGen credentials, a capped two-page budget and Windows RC sign-off',
    nextGate: 'DG7_OPTIONAL_FEATURES_DECIDED',
    authorization: 'provider credentials and spend authorization',
  },
  'local-audio-windows-rc': {
    environment: 'M8_RUN_REAL_E2E',
    reason: 'requires a signed Windows RC and manual audiovisual review; DG2 instead uses S1/S8 synthetic WAVs',
    nextGate: 'DG8_V1_DEBUG_ACCEPTED',
    authorization: 'Windows RC candidate and operator review',
  },
  'presenter-windows-rc': {
    environment: 'PRESENTER_RUN_REAL_E2E',
    reason: 'requires private presenter fixtures, local ASR assets, a signed Windows RC and operator review',
    nextGate: 'DG7_OPTIONAL_FEATURES_DECIDED',
    authorization: 'private fixture access and operator review',
  },
};

export function realFlowEnabled(id: RealFlowId): boolean {
  const configured = process.env[REAL_FLOW_BOUNDARIES[id].environment]?.trim().toLowerCase();
  return configured === '1' || configured === 'true' || configured === 'yes' || configured === 'on';
}

export function realFlowSkipReason(id: RealFlowId): string {
  const boundary = REAL_FLOW_BOUNDARIES[id];
  return `${id}: ${boundary.reason}; next gate ${boundary.nextGate}; authorization: ${boundary.authorization}`;
}
