# Presenter mode RC1 Windows acceptance plan

This checklist is the manual release gate for optional human-presenter mode. Use a disposable workspace and the exact RC installer. Private presenter videos remain local and are identified only by path and SHA-256 in the evidence record.

## Preparation

- [ ] Record the installer version and SHA-256.
- [ ] Resolve every local-only fixture in `tests/fixtures/presenter/manifest.json`.
- [ ] Prepare the 5–8 minute and 15–20 minute videos, no-audio, corrupt, variable-frame-rate/720p, long-silence, Chinese-path and legacy AI project cases.
- [ ] Create a clean evidence directory outside protected production data.

## Full presenter chain

- [ ] Create a project and import the PPT.
- [ ] At step 5 explicitly choose presenter mode and upload the 5–8 minute fixture.
- [ ] Run ASR and slide matching; record elapsed time, peak memory and cache state.
- [ ] Resolve all blocked/review anchors, manually lock at least two boundaries, refresh and restart the app.
- [ ] Confirm the locked revision and timeline hash are unchanged after restart.
- [ ] Preview the first, middle and last pages; verify presenter placement and subtitle safe areas.
- [ ] Render and export the delivery package.
- [ ] Confirm the package contains MP4, SRT, transcript JSON, page matches/anchors, presenter window plan, preflight report, logs and timeline hash.

## Performance and synchronization

- [ ] Run both duration classes and record ASR time, peak memory, cache hit, local recalculation time and final render time.
- [ ] Verify original-audio/video correlation is within 80 ms.
- [ ] Verify subtitle timestamps are within 150 ms.
- [ ] Verify slide/presenter visual changes are within 250 ms using extracted frames.

## Windows installation and recovery

- [ ] Install and launch on Windows 10 and Windows 11 where available.
- [ ] Verify Chinese-path import and occupied-port recovery.
- [ ] Close the app during recognition, relaunch, and resume from the latest safe checkpoint.
- [ ] Close the app during rendering, relaunch, and resume without publishing partial output.
- [ ] Uninstall while preserving projects, then reinstall the same artifact and reopen the project.
- [ ] Record antivirus result or access limitation without inferring a pass.

## Isolation and release decision

- [ ] Run the legacy AI narration project from the same installed RC.
- [ ] Confirm it creates no presenter job, adds no presenter blocker and preserves its prior output contract.
- [ ] Confirm P0 = 0 and P1 = 0; record disposition for every P2.
- [ ] Obtain Windows operator sign-off.

Keep `feature_flags.presenter_mode` at `internal` and report status at `pending_manual_windows` until every release-decision item has evidence. Only then may a separate reviewed change promote it to `stable_optional`.
