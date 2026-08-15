# Troubleshooting workflow

## Gather safe evidence

1. Record the application version, operating system, failing stage, stable error code, and minimal
   reproduction steps.
2. Run the environment diagnostics and inspect component availability, disk space, workspace
   writability, worker health, and stale jobs.
3. Reproduce with synthetic material when possible.
4. Inspect diagnostic archives before sharing them. Remove credentials, headers, absolute private
   paths, source content, audio, and personal data.

## Classify the failure

| Symptom or code | Next action |
| --- | --- |
| `component_missing` | Install or restore the named runtime; do not copy arbitrary system files into a release. |
| `workspace_not_writable` | Select a writable local workspace and rerun the diagnostic. |
| `disk_space_low` | Remove only rebuildable caches after previewing the cleanup plan. |
| `render_input_stale` / `render_input_changed` | Rerun full preflight against the current inputs. |
| `renderer_runtime_unavailable` | Verify Node, Chromium, Remotion, FFmpeg, and FFprobe. |
| `audio_route_mixed` | Choose one project-wide audio route before any external request. |
| `audio_revision_mismatch` | Regenerate or reimport audio for the current narration revision. |
| `transcript_missing` | Complete transcription before subtitle generation. |
| `subtitle_timing_overlap` | Correct word timestamps or page boundaries and rebuild subtitles. |
| `video_preflight_blocked` | Resolve blockers; confirm only explicitly confirmable warnings. |
| `package_hash_mismatch` / `package_size_mismatch` | Reject the package and retrieve or rebuild it. |
| `health_check_failed` / `migration_failed` | Preserve logs and verify automatic rollback before retrying. |

## Handle durable render jobs

- For a long-lived `queued` job, confirm the worker is enabled and awake.
- For `paused`, resume from the recorded checkpoint after verifying inputs.
- For `failed`, keep the stable error code and retry through the supported action.
- For `cancelled`, confirm child processes stopped and keep valid page caches.
- For `stale_running_jobs > 0`, restart the app so they recover to paused, then resume safely.

Never modify SQLite queue rows, cache metadata, or `project.json` as a shortcut.

## Decide whether to change code

Diagnose first. Implement only when the request includes a fix. For a fix, add a deterministic
regression test, run the smallest relevant test repeatedly when a race is suspected, then run the
full repository gate appropriate to the affected platforms.
