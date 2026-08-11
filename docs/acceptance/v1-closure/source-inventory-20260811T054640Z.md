# G0 源码与工件分类清单

<!-- prettier-ignore-start -->

- Run ID: `20260811T054640Z`
- Snapshot source: `git status --porcelain=v1` on `recovery/root-snapshot-20260810@117fb60cbb0ca877c0920a26f5ceb31d8e42e901`.
- Inventory entries: 151; tracked modifications: 49; untracked entries: 102.
- Decision rule: this is a handling classification, not permission to delete, move, stage, or overwrite any item.

## Summary

| Classification | Entries |
| --- | ---: |
| application_source | 53 |
| archive_or_log | 4 |
| backup | 1 |
| build_release_tooling | 10 |
| contract | 3 |
| documentation_or_evidence | 23 |
| generated_cache | 6 |
| migration | 3 |
| release_artifact | 2 |
| test_or_fixture | 41 |
| unknown | 5 |

## Entry inventory

| # | Git | Path | Classification | Proposed treatment | Rationale |
| ---: | --- | --- | --- | --- | --- |
| 1 | `M` | `.github/workflows/ci.yml` | build_release_tooling | review_and_assign_owner | CI、打包、安装或发布验收工具 |
| 2 | `M` | `Run-P01-V4-PathSafe-Rebuild.ps1` | build_release_tooling | review_and_assign_owner | CI、打包、安装或发布验收工具 |
| 3 | `M` | `apps/api/src/workbench/api/assets.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 4 | `M` | `apps/api/src/workbench/api/preflight.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 5 | `M` | `apps/api/src/workbench/api/timeline_production.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 6 | `M` | `apps/api/src/workbench/api/video.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 7 | `M` | `apps/api/src/workbench/assets/models.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 8 | `M` | `apps/api/src/workbench/assets/service.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 9 | `M` | `apps/api/src/workbench/domain/issues.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 10 | `M` | `apps/api/src/workbench/effects/rc_manifest.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 11 | `M` | `apps/api/src/workbench/effects/release_models.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 12 | `M` | `apps/api/src/workbench/main.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 13 | `M` | `apps/api/src/workbench/preflight/engine.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 14 | `M` | `apps/api/src/workbench/rendering/compiler.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 15 | `M` | `apps/api/src/workbench/rendering/export_pipeline.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 16 | `M` | `apps/api/src/workbench/rendering/models.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 17 | `M` | `apps/api/src/workbench/rendering/preview.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 18 | `M` | `apps/api/src/workbench/rendering/remotion_runner.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 19 | `M` | `apps/api/src/workbench/services/preflight_service.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 20 | `M` | `apps/api/src/workbench/storage/migrations.py` | migration | review_and_assign_owner | 数据库或项目兼容迁移 |
| 21 | `M` | `apps/api/src/workbench/storage/workspace_db.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 22 | `M` | `apps/api/src/workbench/video/render_job.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 23 | `M` | `apps/web/src/api/client.ts` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 24 | `M` | `apps/web/src/app/styles.css` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 25 | `M` | `apps/web/src/features/preflight/PreflightWorkspace.test.tsx` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 26 | `M` | `apps/web/src/features/preflight/PreflightWorkspace.tsx` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 27 | `M` | `apps/web/src/features/timeline/timelineEditor.test.ts` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 28 | `M` | `apps/web/src/features/timeline/timelineEditor.ts` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 29 | `M` | `apps/web/src/features/video/PreviewWorkspace.tsx` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 30 | `M` | `apps/web/src/features/workflow/WorkflowShell.tsx` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 31 | `M` | `docs/effects/release-candidate-manifest.json` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 32 | `M` | `installer/workbench.iss` | build_release_tooling | review_and_assign_owner | CI、打包、安装或发布验收工具 |
| 33 | `M` | `remotion/src/render-graph/types.ts` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 34 | `M` | `schemas/render-graph-v2.schema.json` | contract | review_and_assign_owner | 版本化 schema 或跨端契约 |
| 35 | `M` | `scripts/build-release.ps1` | build_release_tooling | review_and_assign_owner | CI、打包、安装或发布验收工具 |
| 36 | `M` | `scripts/freeze-release.ps1` | build_release_tooling | review_and_assign_owner | CI、打包、安装或发布验收工具 |
| 37 | `M` | `scripts/windows_acceptance_report.py` | build_release_tooling | review_and_assign_owner | CI、打包、安装或发布验收工具 |
| 38 | `M` | `tests/integration/test_asset_routes.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 39 | `M` | `tests/integration/test_render_graph_routes.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 40 | `M` | `tests/release/test_build_release_script.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 41 | `M` | `tests/release/test_launcher_contract.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 42 | `M` | `tests/release/test_release_freeze.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 43 | `M` | `tests/release/test_windows_acceptance_report.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 44 | `M` | `tests/release/windows-acceptance.ps1` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 45 | `M` | `tests/unit/rendering/test_export_pipeline.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 46 | `M` | `tests/unit/rendering/test_remotion_runner.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 47 | `M` | `tests/unit/rendering/test_render_graph_v2.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 48 | `M` | `tests/unit/storage/test_workspace_migrations.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 49 | `M` | `tests/unit/video/test_render_job_v2.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 50 | `??` | `.git.broken-pointer-20260810-183914.txt` | unknown | manual_review_required | 无法仅由路径判断来源或提交归属 |
| 51 | `??` | `.pnpm-store/` | generated_cache | exclude_from_clean_source_commit | 本地缓存或临时测试数据 |
| 52 | `??` | `.superpowers/` | unknown | manual_review_required | 无法仅由路径判断来源或提交归属 |
| 53 | `??` | `.tmp-s1-frozen-smoke/` | generated_cache | exclude_from_clean_source_commit | 本地缓存或临时测试数据 |
| 54 | `??` | `.tmp-s1-schema-probe/` | generated_cache | exclude_from_clean_source_commit | 本地缓存或临时测试数据 |
| 55 | `??` | `.tmp/` | generated_cache | exclude_from_clean_source_commit | 本地缓存或临时测试数据 |
| 56 | `??` | `README-P01-Graceful-Shutdown-V11.txt` | documentation_or_evidence | review_and_assign_owner | 恢复或操作说明 |
| 57 | `??` | `README-P01-Installer-Lock-V7.txt` | documentation_or_evidence | review_and_assign_owner | 恢复或操作说明 |
| 58 | `??` | `README-P01-Onedir-V10.txt` | documentation_or_evidence | review_and_assign_owner | 恢复或操作说明 |
| 59 | `??` | `README-P01-Startup-Diagnostics-V8.txt` | documentation_or_evidence | review_and_assign_owner | 恢复或操作说明 |
| 60 | `??` | `README-P01-VC-Runtime-V9.txt` | documentation_or_evidence | review_and_assign_owner | 恢复或操作说明 |
| 61 | `??` | `README-P02-Health-Diagnostics-V1.txt` | documentation_or_evidence | review_and_assign_owner | 恢复或操作说明 |
| 62 | `??` | `README-P02-Health-Diagnostics-V2.txt` | documentation_or_evidence | review_and_assign_owner | 恢复或操作说明 |
| 63 | `??` | `README-P02-Health-Diagnostics-V3.txt` | documentation_or_evidence | review_and_assign_owner | 恢复或操作说明 |
| 64 | `??` | `README-r23.md` | documentation_or_evidence | review_and_assign_owner | 恢复或操作说明 |
| 65 | `??` | `README-r24.md` | documentation_or_evidence | review_and_assign_owner | 恢复或操作说明 |
| 66 | `??` | `apps.zip` | archive_or_log | preserve_outside_source_commit | 恢复压缩包、构建诊断或历史日志 |
| 67 | `??` | `apps/api/src/workbench/api/migrations.py` | migration | review_and_assign_owner | 数据库或项目兼容迁移 |
| 68 | `??` | `apps/api/src/workbench/assets/audio_executor.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 69 | `??` | `apps/api/src/workbench/assets/image_executor.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 70 | `??` | `apps/api/src/workbench/assets/video_executor.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 71 | `??` | `apps/api/src/workbench/cache/contracts.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 72 | `??` | `apps/api/src/workbench/cache/gc.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 73 | `??` | `apps/api/src/workbench/cache/invalidation.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 74 | `??` | `apps/api/src/workbench/cache/models.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 75 | `??` | `apps/api/src/workbench/cache/persistent_gc.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 76 | `??` | `apps/api/src/workbench/cache/persistent_repository.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 77 | `??` | `apps/api/src/workbench/cache/repository.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 78 | `??` | `apps/api/src/workbench/desktop/` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 79 | `??` | `apps/api/src/workbench/media/probe.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 80 | `??` | `apps/api/src/workbench/media/waveform.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 81 | `??` | `apps/api/src/workbench/migrations/` | migration | review_and_assign_owner | 数据库或项目兼容迁移 |
| 82 | `??` | `apps/api/src/workbench/rendering/legacy_adapter.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 83 | `??` | `apps/api/src/workbench/rendering/preview_service.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 84 | `??` | `apps/api/src/workbench/rendering/project_reader.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 85 | `??` | `apps/api/src/workbench/rendering/range_projection.py` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 86 | `??` | `apps/api/workbench-launcher.spec` | build_release_tooling | review_and_assign_owner | CI、打包、安装或发布验收工具 |
| 87 | `??` | `apps/web/src/features/cache/` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 88 | `??` | `apps/web/src/features/timeline/EnhancedTimelineWorkspace.tsx` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 89 | `??` | `apps/web/src/features/timeline/editorStore.test.ts` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 90 | `??` | `apps/web/src/features/timeline/editorStore.ts` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 91 | `??` | `apps/web/src/features/video/AuthoritativePreviewPanel.test.tsx` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 92 | `??` | `apps/web/src/features/video/AuthoritativePreviewPanel.tsx` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 93 | `??` | `apps/web/src/features/video/TaskCenter.test.tsx` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 94 | `??` | `apps/web/src/features/video/TaskCenter.tsx` | application_source | review_and_assign_owner | 应用实现或前端/Remotion 接线 |
| 95 | `??` | `backup/` | backup | preserve_for_forensics | 恢复备份或历史项目材料 |
| 96 | `??` | `build-pyinstaller-diagnosis_20260806_153916.txt` | unknown | manual_review_required | 无法仅由路径判断来源或提交归属 |
| 97 | `??` | `build-pyinstaller-mirror_20260806_155217.txt` | unknown | manual_review_required | 无法仅由路径判断来源或提交归属 |
| 98 | `??` | `build-pyinstaller-real_20260806_154544.txt` | unknown | manual_review_required | 无法仅由路径判断来源或提交归属 |
| 99 | `??` | `cache/acceptance-frames/` | generated_cache | exclude_from_clean_source_commit | 本地缓存或临时测试数据 |
| 100 | `??` | `cache/acceptance-office/` | generated_cache | exclude_from_clean_source_commit | 本地缓存或临时测试数据 |
| 101 | `??` | `docs/acceptance/foundation/stop-points/2026-08-11-p2-asset-derivatives-g2.json` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 102 | `??` | `docs/acceptance/foundation/stop-points/2026-08-11-p3-authoritative-preview-g3.json` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 103 | `??` | `docs/acceptance/foundation/stop-points/2026-08-11-p4-cache-invalidation-g4.json` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 104 | `??` | `docs/acceptance/foundation/stop-points/2026-08-11-p5-legacy-migration-g5.json` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 105 | `??` | `docs/acceptance/v1-closure/` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 106 | `??` | `docs/acceptance/windows-release-baseline.md` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 107 | `??` | `docs/superpowers/plans/2026-08-11-mainline-development-orchestration.md` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 108 | `??` | `docs/superpowers/plans/2026-08-11-v1-production-closure.md` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 109 | `??` | `docs/superpowers/plans/2026-08-11-windows-release-stability-and-full-chain-acceptance.md` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 110 | `??` | `docs/superpowers/specs/2026-08-11-mainline-development-orchestration-design.md` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 111 | `??` | `docs/superpowers/specs/2026-08-11-v1-production-closure-design.md` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 112 | `??` | `docs/superpowers/specs/2026-08-11-windows-release-stability-and-full-chain-acceptance-design.md` | documentation_or_evidence | review_and_assign_owner | 设计、计划、基线或验收证据 |
| 113 | `??` | `frontend-contract-files.zip` | archive_or_log | preserve_outside_source_commit | 恢复压缩包、构建诊断或历史日志 |
| 114 | `??` | `release-effect-v2/` | release_artifact | exclude_from_clean_source_commit | 历史安装包或发布工件 |
| 115 | `??` | `release/` | release_artifact | exclude_from_clean_source_commit | 历史安装包或发布工件 |
| 116 | `??` | `schemas/cache-dependency-v1.schema.json` | contract | review_and_assign_owner | 版本化 schema 或跨端契约 |
| 117 | `??` | `schemas/windows-release-acceptance-v2.schema.json` | contract | review_and_assign_owner | 版本化 schema 或跨端契约 |
| 118 | `??` | `scripts/release_artifacts.py` | build_release_tooling | review_and_assign_owner | CI、打包、安装或发布验收工具 |
| 119 | `??` | `scripts/run-web-release-gate.ps1` | build_release_tooling | review_and_assign_owner | CI、打包、安装或发布验收工具 |
| 120 | `??` | `scripts/windows_acceptance/` | build_release_tooling | review_and_assign_owner | CI、打包、安装或发布验收工具 |
| 121 | `??` | `tests/acceptance/windows/` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 122 | `??` | `tests/fixtures/cache-dependency-v1.json` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 123 | `??` | `tests/fixtures/legacy-project-v1.json` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 124 | `??` | `tests/integration/test_legacy_project_acceptance.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 125 | `??` | `tests/integration/test_preflight_determinism.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 126 | `??` | `tests/integration/test_project_v2_migration.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 127 | `??` | `tests/integration/test_render_interruption_recovery.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 128 | `??` | `tests/release/test_build_release_script.py.before-launcher-encoding-test-20260804_140356.bak` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 129 | `??` | `tests/release/test_build_release_script.py.before-runtime-fix-20260804_135121.bak` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 130 | `??` | `tests/release/test_gui_launcher_contract.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 131 | `??` | `tests/release/test_release_artifacts.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 132 | `??` | `tests/release/test_web_release_gate_contract.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 133 | `??` | `tests/release/test_windows_full_chain_contract.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 134 | `??` | `tests/release/test_windows_playback_and_render_evidence.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 135 | `??` | `tests/unit/api/` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 136 | `??` | `tests/unit/assets/test_audio_derivative_executor.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 137 | `??` | `tests/unit/assets/test_derivative_job_service.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 138 | `??` | `tests/unit/assets/test_image_derivative_executor.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 139 | `??` | `tests/unit/assets/test_video_derivative_executor.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 140 | `??` | `tests/unit/cache/test_dependency_contracts.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 141 | `??` | `tests/unit/cache/test_gc_policy.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 142 | `??` | `tests/unit/cache/test_invalidation_policy.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 143 | `??` | `tests/unit/cache/test_persistent_repository.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 144 | `??` | `tests/unit/desktop/` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 145 | `??` | `tests/unit/media/test_probe.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 146 | `??` | `tests/unit/media/test_waveform.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 147 | `??` | `tests/unit/rendering/test_legacy_adapter.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 148 | `??` | `tests/unit/rendering/test_preview_service.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 149 | `??` | `tests/unit/rendering/test_range_projection.py` | test_or_fixture | review_and_assign_owner | 自动化、验收或迁移 fixture |
| 150 | `??` | `web-typecheck-error.log` | archive_or_log | preserve_outside_source_commit | 恢复压缩包、构建诊断或历史日志 |
| 151 | `??` | `web-vitest-error.log` | archive_or_log | preserve_outside_source_commit | 恢复压缩包、构建诊断或历史日志 |

## G0 follow-up

- All application_source, migration, contract, test_or_fixture, build_release_tooling, and documentation_or_evidence entries require an owner and commit decision in T02/T03.
- generated_cache, release_artifact, archive_or_log, and backup entries are preserved but excluded from the clean source checkpoint unless an explicit evidence manifest requires a copy.
- unknown entries require manual provenance review before any cleanup, staging, or integration action.

## T01 scan results

- Git ignore coverage was extended for local dependency stores, temporary recovery copies, generated acceptance frames, recovery backups, release artifacts, archives, and diagnostic logs. Reviewable evidence remains under `docs/acceptance/`.
- The focused security suite passed 14 tests. Pattern hits in source search were configuration, redaction, API, or test files; no plaintext credential finding was recorded.
- No source-path file exceeding 5 MiB was found after excluding dependencies, recovery, release, cache, and temporary directories.
- Tracked path name matches for diagnostics/projects were application and test modules, not workspace-data or user project artifacts.

<!-- prettier-ignore-end -->
