# Local PPT Video Workbench v1.0.0 Release Notes / 发布说明

status: RC candidate — pending manual Windows sign-off  
version: `v1.0.0`  
candidate: `RC1`  
release tag: not created

## Scope / 范围

This candidate consolidates the local PPT-to-video workflow delivered through
M1–M7 and the M8 acceptance harness:

- project and material management for Word, PPTX and PDF inputs;
- OCR, page matching, narration editing and confirmed-version gates;
- local audio transcription, diff review, pagination and subtitle generation;
- Remotion preview, technology-board templates, preflight and recoverable render;
- MP4/SRT/DOCX/audio/package export with checksums and audit records;
- Windows installation, launcher, doctor, update and rollback workflows;
- traceability, RC automation, performance budgets and release security checks.

该候选版本整合 M1—M7 的本地 PPT 转视频流程，以及 M8 的验收自动化、追踪矩阵、
性能预算和发布安全门禁。

## Verification status / 验证状态

Linux automated checks are recorded in `M8-GATE.md` and the RC1 evidence
manifest. Real Windows/Office/manual audiovisual acceptance is still
`pending_manual_windows`; therefore this document must not be treated as a
final v1.0.0 release announcement and no release tag has been created.

Linux 自动化检查已记录在 `M8-GATE.md` 与 RC1 证据清单中。真实 Windows/Office/
人工视听验收仍为 `pending_manual_windows`，因此本文件当前不能视为正式 v1.0.0
发布公告，且尚未创建发布标签。

## Known release gate / 当前发布门禁

The release freeze script refuses to proceed until the RC1 manifest has
`status: signed`, `signoff.signed: true`, passed artifact and scenario results,
and assessed P0/P1 defects.

发布冻结脚本会在 RC1 清单满足 `status: signed`、`signoff.signed: true`、产物与场景
全部通过且 P0/P1 缺陷已评估前拒绝继续。
