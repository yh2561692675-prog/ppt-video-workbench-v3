# Effect Engine RC1 acceptance report

Status: **pending_manual_windows**

This report contains preparation evidence only. It does not claim installer, GUI, Windows rendering, antivirus, or manual acceptance results.

## Automated evidence

| Area                                   | Result                                              |
| -------------------------------------- | --------------------------------------------------- |
| EffectPlan V2 contract and migration   | Passed in focused contract tests                    |
| Templates and interpreter              | Passed in Remotion tests and typecheck              |
| 40-page visual manifest structure      | Passed: 40 pages, 10 categories, both aspect ratios |
| Batch recovery and presenter collision | Passed: 3 integration tests                         |
| Windows installer / GUI / real project | Not run; manual gate required                       |

## Manual evidence placeholders

- Windows launch/project-center screenshot: received from user (`codex-clipboard-fb5baffa-e492-4503-b7b6-8f29691925e3.png`); confirms the local UI is open at `127.0.0.1:27268`. This is partial evidence only.
- Existing project preview/preflight screenshot: `.tmp/acceptance-step6-preflight-passed.png`; project `航空航天`, step 6, 8 pages, complete preflight and structured preflight both shown as passed. Rendering was not started.
- End-page preview screenshot: `.tmp/acceptance-step6-page8.png`; page selector visibly shows page 8 `未来趋势与报考建议`, with preflight still passed. Rendering was not started.
- Preview playback check: real browser UI reported `0:02 / 8:02` and `预览播放中`, then was paused successfully. No render/export was triggered.
- Isolated render evidence: temporary workspace `F:\ppt-video-workbench-v3\.tmp\workspace-acceptance` rendered the copied `航空航天` project; UI reached step 7 and shows “完整预检已通过，可以开始渲染与导出”。 Screenshot: `.tmp/acceptance-step7-render-ready.png`.
- Output evidence: `最终视频.mp4` (84,718,309 bytes, SHA-256 `329AAF25E902EBEC6FB2023097FCF02944CCFA6C8D4801876D4A204229DC8180`), `字幕.srt` (15,137 bytes, SHA-256 `C468A0B04616FA4525EA6D6851221B79A71BFF37D626517F24BAB1AC4BE6DE48`).
- Render frame evidence extracted from the temporary MP4: `.tmp/acceptance-render-start.jpg`, `.tmp/acceptance-render-middle.jpg`, `.tmp/acceptance-render-end.jpg`; all three show valid 16:9 content and subtitles without black-frame output.
- Restart recovery: temporary API was stopped and restarted on port `28888`; `/api/health` returned 200, the copied project reappeared at current step 7, and MP4/SRT hashes remained unchanged.
- Installer version/hash: pending
- Preview screenshots: pending
- MP4/SRT output hashes: pending
- Restart recovery log: pending
- Windows operator sign-off: pending

Do not change this status to passed without the evidence in `tests/acceptance/effect-engine-plan.md`.
