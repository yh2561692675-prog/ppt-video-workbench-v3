# Effect Engine RC1 Windows acceptance plan

This checklist is a manual gate. It must be executed on a real Windows desktop with the RC installer and a disposable project. Do not use `F:\Video\workspace.db` as a test database, and do not modify `F:\app\app` as source.

## Preparation

- [ ] Confirm installer path and SHA-256 with the release owner.
- [ ] Copy the supplied reference MP4 to a disposable workspace if needed.
- [ ] Create a disposable 6-page and a 40-page project; keep source files outside the protected paths.

## Acceptance steps

- [ ] Install the RC package and record installer version.
- [ ] Start the application and confirm the project opens.
- [ ] Run complete preview with EffectPlan revision/hash visible.
- [ ] Render the first template batch: ProgressiveReveal, ChapterCurtain, StatCounter, ChartNarration, CompareMode, FocusSpotlight.
- [ ] Render the second template batch: CardStack, GaugeAndRatio, PathBuilder, TagMatrix, RiskAlert, MapHighlight.
- [ ] Verify both 16:9 and 9:16 outputs and subtitle safe areas.
- [ ] Verify audio/subtitle/presenter timing and presenter collision fallback.
- [ ] Inject one page failure, confirm SafeSlide fallback, continuation, restart recovery, and local rerender.
- [ ] Export MP4 and SRT; record output paths and hashes.

## Evidence required

- [ ] Screenshots: install, launch, first/middle/last preview frames, fallback, recovery.
- [ ] Logs: batch status, failed page, retry count, fallback template, final output hash.
- [ ] Manual sign-off by the Windows operator.

Until every checkbox above has real evidence, release status remains `pending_manual_windows`.
