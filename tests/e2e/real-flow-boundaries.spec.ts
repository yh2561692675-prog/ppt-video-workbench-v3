import { expect, test } from '@playwright/test';

import { REAL_FLOW_BOUNDARIES, type RealFlowId } from './real-flow-policy';

const REQUIRED_IDS: RealFlowId[] = [
  'heygen-two-page',
  'local-audio-windows-rc',
  'presenter-windows-rc',
];

test('every real-flow boundary has an authorized, finite destination', () => {
  expect(Object.keys(REAL_FLOW_BOUNDARIES).sort()).toEqual([...REQUIRED_IDS].sort());
  for (const boundary of Object.values(REAL_FLOW_BOUNDARIES)) {
    expect(boundary.environment).toMatch(/^[A-Z0-9_]+$/);
    expect(boundary.reason.length).toBeGreaterThan(20);
    expect(boundary.authorization.length).toBeGreaterThan(10);
    expect(['DG7_OPTIONAL_FEATURES_DECIDED', 'DG8_V1_DEBUG_ACCEPTED']).toContain(boundary.nextGate);
  }
});
