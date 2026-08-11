# Presenter mode RC1 acceptance report

Status: **pending_manual_windows**

Feature flag: **internal**

This report records automated evidence only. It does not claim Windows operator sign-off, private-fixture performance, unrestricted antivirus acceptance, or release readiness.

## Automated evidence

| Area                                                  | Result                                              |
| ----------------------------------------------------- | --------------------------------------------------- |
| P00–P04 compatibility, media, ASR and matching        | Passed focused Python tests                         |
| P05 locked timeline and revision conflicts            | Passed focused API and timeline tests               |
| P06 shared subtitle/effect adapters and props hash    | Passed Python and Remotion contract tests           |
| P07 placement and collision avoidance                 | Passed focused placement tests                      |
| P08 single presenter source and master audio contract | Passed Remotion tests and typecheck                 |
| P09 six-zone review UI and explicit opt-in entry      | Passed component tests and browser workflow         |
| P10 checkpoint recovery and invalidation              | Passed focused recovery tests                       |
| P11 structured issues and presenter fallback          | Passed focused preflight/fallback tests             |
| P12 mocked browser contract and release-state guard   | Automated portion passed; real fixture gate pending |

The automated API chain writes transcript, matches, presenter timeline, subtitle timeline and SRT atomically. Video props use presenter anchors as page ranges, and final muxing seeks the single presenter master source rather than synthesizing page narration audio.

## Required delivery evidence

- MP4 and SRT with recorded SHA-256 values
- `presenter/transcript.json`
- `presenter/matches.json` containing page anchors
- `presenter/timeline.json` containing presenter placement segments and timeline hash
- structured preflight report and log manifest
- first/middle/last extracted frames
- restart recovery record with unchanged locked timeline hash

## Manual evidence placeholders

- 5–8 minute private fixture path and hash: pending
- 15–20 minute private fixture path and hash: pending
- ASR duration and peak memory: pending
- cache hit and local recalculation timing: pending
- final render timing: pending
- original audio/video correlation <= 80 ms: pending
- subtitle timing <= 150 ms: pending
- slide/presenter visual timing <= 250 ms: pending
- Windows 10/11 install, Chinese path and port recovery: pending
- recognition/render forced-close recovery: pending
- uninstall preservation and same-artifact reinstall: pending
- legacy AI-mode full-project regression on the installed RC: pending
- antivirus result: pending
- P0/P1/P2 triage and Windows operator sign-off: pending

Do not change the report to passed or promote `feature_flags.presenter_mode` to `stable_optional` until every checkbox in `tests/acceptance/presenter-mode-plan.md` has real evidence.
