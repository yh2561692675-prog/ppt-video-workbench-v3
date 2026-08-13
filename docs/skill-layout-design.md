# Skill layout design

## Goal

Package the repository's repeatable PPT-to-video operating knowledge as a portable Codex skill
without moving or duplicating the application source tree.

## Decision

Keep the application at the repository root and add one independently installable skill at
`skills/ppt-video-workbench`:

```text
skills/
└── ppt-video-workbench/
    ├── SKILL.md
    ├── agents/
    │   └── openai.yaml
    ├── references/
    │   ├── source-workflow.md
    │   ├── troubleshooting.md
    │   └── maintenance.md
    └── scripts/
        └── preflight.py
```

This follows the Agent Skills progressive-disclosure model:

1. Codex always sees only the skill name and description.
2. Codex reads `SKILL.md` when the request matches.
3. Codex reads a reference or runs the preflight script only when the selected workflow needs it.

## Boundaries

- Do not copy application code, lockfiles, fixtures, or generated media into the skill.
- Do not place a second README, changelog, installation guide, or empty resource directory inside
  the skill.
- Keep user-facing repository documentation at the root and detailed agent-only procedures inside
  the skill.
- Treat external LLM and HeyGen access as optional. Never request, print, or persist credentials.
- Treat rendering, cleanup, release publication, and dependency updates as explicit workflows with
  their existing repository gates.

## Validation

- Validate the skill with the official `quick_validate.py` helper.
- Test `scripts/preflight.py` both inside and outside a repository.
- Confirm all relative links from `SKILL.md` resolve.
- Run repository formatting and documentation-link tests before publication.
