---
name: ppt-video-workbench
description: Operate, validate, troubleshoot, and maintain the PPT Video Workbench local-first presentation-to-video repository. Use when Codex needs to set up or run the Python/FastAPI, React/Vite, Remotion, and FFmpeg source workflow; turn PPTX, DOCX, PDF, images, narration, or audio into an auditable video project; diagnose import, audio, subtitle, preflight, render, packaging, or recovery failures; or review Issues, pull requests, dependency updates, and source releases for this repository.
---

# PPT Video Workbench

Use the repository as a local-first, auditable workbench. Preserve source inputs, project
manifests, revisions, preflight evidence, and previously successful outputs.

## Start here

1. Locate the repository root by finding both `pyproject.toml` and `pnpm-workspace.yaml`.
2. Run `python skills/ppt-video-workbench/scripts/preflight.py --repo <root>` before installing,
   starting, troubleshooting, or releasing the project.
3. Report missing tools and unexpected repository shape before changing files.
4. Select exactly one workflow below and read its reference.

## Select a workflow

- **Set up, start, or produce a video:** Read [references/source-workflow.md](references/source-workflow.md).
- **Diagnose a failed import, audio, subtitle, render, or recovery step:** Read
  [references/troubleshooting.md](references/troubleshooting.md).
- **Triage Issues, review PRs, update dependencies, or publish a release:** Read
  [references/maintenance.md](references/maintenance.md).

Do not read every reference by default.

## Non-negotiable safety rules

- Never request that credentials be pasted into chat, committed, written to `.env.example`, or
  included in logs, screenshots, Issues, PRs, diagnostic archives, or release artifacts.
- Keep the API bound to `127.0.0.1` unless the user explicitly requests and approves a reviewed
  network-exposure change.
- Use synthetic or user-authorized material for reproduction. Do not upload private presentations,
  audio, project data, or diagnostic archives to external services without explicit authorization.
- Do not mix local-recording and HeyGen audio routes in one project. Confirm replacement before a
  paid or irreversible external request.
- Run preflight after any input, narration, audio, subtitle, effect, or template change; do not reuse
  stale evidence.
- Do not delete project manifests, source inputs, settings, or final production packages to fix a
  cache or worker problem.
- Do not claim a Windows installer, signature, manual acceptance, security fix, or release passed
  unless the corresponding evidence actually exists.

## Finish with evidence

State the workflow used, commands run, tests or gates passed, artifacts created, unresolved risks,
and any operation intentionally not performed. Link public Issues, PRs, and releases when working
on repository maintenance.
