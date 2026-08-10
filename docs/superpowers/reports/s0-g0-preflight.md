# S0 G0 Repository Preflight

- Checked at: 2026-08-08 (Asia/Singapore)
- Intended Windows source: `F:\ppt-video-workbench-v3`
- Connected source snapshot: `58e98ed6cc15446ac1387fec208612c1f727f2d0`
- Commit subject: `fix: expand short installer payload path`
- Source branch: `master`
- Execution branch: `feature/s0-peripheral-platform`
- Source worktree state before branching: clean

## Required entry points

| Planned responsibility        | Actual repository path                          | Result                     |
| ----------------------------- | ----------------------------------------------- | -------------------------- |
| Workbench application factory | `apps/api/src/workbench/main.py`                | Present                    |
| Workbench peripheral settings | `apps/api/src/workbench/settings/peripheral.py` | G0-approved creation point |
| Workbench peripheral routes   | `apps/api/src/workbench/api/peripheral.py`      | G0-approved creation point |
| Windows launcher              | `scripts/launcher.ps1`                          | Present                    |
| Windows release builder       | `scripts/build-release.ps1`                     | Present                    |

The earlier `api/main.py` and `api/config.py` paths do not exist in this repository. The S0
implementation plan is therefore amended to follow the established `workbench` package layout.
No production code was written before this mapping was frozen.

## Baseline

Command:

```text
<source-repo>/.venv/bin/python -m pytest -q
```

Result: `254 passed, 1 warning in 20.99s`. The warning is the pre-existing FastAPI TestClient
deprecation warning emitted by the installed dependency.

## Environment boundary

The connected execution environment provides Python 3.12.13 but does not provide Windows
PowerShell. G0 through G4 can be implemented and verified here. G5 PowerShell, PyInstaller and
clean-Windows smoke gates must be rerun from the intended Windows source before release.
