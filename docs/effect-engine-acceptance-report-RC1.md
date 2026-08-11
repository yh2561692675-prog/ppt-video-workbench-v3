# Effect Engine RC1 acceptance report

Status: **pending_manual_windows**

This report contains automated and isolated Windows evidence. It does not claim formal operator sign-off or unrestricted antivirus acceptance.

## Automated evidence

| Area                                   | Result                                                          |
| -------------------------------------- | --------------------------------------------------------------- |
| EffectPlan V2 contract and migration   | Passed in focused contract tests                                |
| Templates and interpreter              | Passed in Remotion tests and typecheck                          |
| 40-page visual manifest structure      | Passed: 40 pages, 10 categories, both aspect ratios             |
| Batch recovery and presenter collision | Passed: 3 integration tests                                     |
| Windows installer / GUI / real project | Installer + isolated API/UI verified; operator sign-off pending |

## Manual evidence placeholders

- Windows launch/project-center screenshot: received from user (`codex-clipboard-fb5baffa-e492-4503-b7b6-8f29691925e3.png`); confirms the local UI is open at `127.0.0.1:27268`. This is partial evidence only.
- Existing project preview/preflight screenshot: `.tmp/acceptance-step6-preflight-passed.png`; project `航空航天`, step 6, 8 pages, complete preflight and structured preflight both shown as passed. Rendering was not started.
- End-page preview screenshot: `.tmp/acceptance-step6-page8.png`; page selector visibly shows page 8 `未来趋势与报考建议`, with preflight still passed. Rendering was not started.
- Preview playback check: real browser UI reported `0:02 / 8:02` and `预览播放中`, then was paused successfully. No render/export was triggered.
- Isolated render evidence: temporary workspace `F:\ppt-video-workbench-v3\.tmp\workspace-acceptance` rendered the copied `航空航天` project; UI reached step 7 and shows “完整预检已通过，可以开始渲染与导出”。 Screenshot: `.tmp/acceptance-step7-render-ready.png`.
- Output evidence: `最终视频.mp4` (84,718,309 bytes, SHA-256 `329AAF25E902EBEC6FB2023097FCF02944CCFA6C8D4801876D4A204229DC8180`), `字幕.srt` (15,137 bytes, SHA-256 `C468A0B04616FA4525EA6D6851221B79A71BFF37D626517F24BAB1AC4BE6DE48`).
- Render frame evidence extracted from the temporary MP4: `.tmp/acceptance-render-start.jpg`, `.tmp/acceptance-render-middle.jpg`, `.tmp/acceptance-render-end.jpg`; all three show valid 16:9 content and subtitles without black-frame output.
- Restart recovery: temporary API was stopped and restarted on port `28888`; `/api/health` returned 200, the copied project reappeared at current step 7, and MP4/SRT hashes remained unchanged.
- Installer package: `release/ppt-video-workbench-setup.exe`, SHA-256 `BA588D7675A767B025C3783E3922153D0F223CA8C372B2C0E269FABAA8E68284`.
- Installer attempt 1: exit code 4 and rollback because the restricted runner denied the HKCU uninstall key (`RegCreateKeyEx code 5`) and desktop shortcut save (`IPersistFile::Save code 0x80070005`). This is recorded as a permission boundary, not a product pass.
- Installer attempt 2: elevated, still isolated to `F:\ppt-video-workbench-v3\.tmp\installed-acceptance-elevated`, exit code 0. `release/api/workbench.exe`, `release/web/index.html`, `release/runtime/node/node.exe`, and `unins000.exe` are present. Installed API SHA-256: `69E8FBD0F095BA799E660ABA9E29EA5F8B0570C7A49B26846B205F5C78050B62`.
- Installed-runtime smoke check: API `http://127.0.0.1:29999/api/health` returned HTTP 200/status `ok`; Web root returned HTTP 200; one temporary project was listed at current step 7; POST `/video/preflight` returned HTTP 200 with `allowed=true` and an empty `issues` array.
- Antivirus status: `Get-MpComputerStatus` was attempted read-only but returned `Access denied`; no antivirus claim is made.
- Preview screenshots: recorded above (`.tmp/acceptance-step6-preflight-passed.png`, `.tmp/acceptance-step7-render-ready.png`, and frame evidence).
- MP4/SRT output hashes: recorded above.
- Restart recovery log: recorded above and in the implementation log.
- Windows operator sign-off: pending

Do not change this status to passed without the evidence in `tests/acceptance/effect-engine-plan.md`.
