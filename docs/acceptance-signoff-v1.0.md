# V1.0 Acceptance Sign-off / V1.0 验收签署

status: blocked_pending_manual_signoff  
release: v1.0.0  
candidate: RC1  
evidence: `tests/acceptance/results/RC1/evidence-manifest.json`

## Current decision / 当前结论

The release is blocked by `pending_manual_windows`. The automated Linux
evidence is complete for this candidate, but the v1.0.0 sign-off remains
unsigned until the clean Windows 10/11 acceptance run is completed.

当前版本被 `pending_manual_windows` 阻断。Linux 自动化证据已完成，但在干净的
Windows 10/11 环境完成验收前，v1.0.0 不得签署。

## Required sign-off evidence / 必须补齐的证据

- [ ] Clean Windows 10/11 VM with a real Office installation
- [ ] Word/PPTX/searchable PDF/scanned PDF/MP3/WAV import and project lifecycle
- [ ] Multi-image natural sort and manual sort correction
- [ ] Local audio full chain with transcription, diff, pagination and export
- [ ] Real voice and HeyGen scenarios, with paid requests explicitly recorded
- [ ] Recovery, retry, update, rollback, shortcut and browser-open checks
- [ ] Manual audiovisual review of MP4, subtitles and narration alignment
- [ ] P0/P1 defects assessed and closed

## Signature / 签署

```yaml
signed: false
signer: pending_manual_windows
signed_at: null
notes: Complete the RC1 evidence manifest before changing signed to true.
```

This file is a sign-off template, not evidence of release approval.

此文件是签署模板，不代表版本已获批准发布。
