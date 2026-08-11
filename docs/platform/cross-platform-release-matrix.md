# Cross-platform release matrix

This matrix is the release gate for B10/B11. The implementation keeps
platform-specific behavior behind `PlatformServices`; the Windows path is the
current production baseline, while macOS/Linux entries remain explicit PoC
targets until evidence is produced on those operating systems.

| Capability | Windows | macOS | Linux | Evidence required |
| --- | --- | --- | --- | --- |
| logical paths / Unicode | implemented | contract-tested only | contract-tested only | path containment + Unicode fixtures |
| atomic files / WAL | implemented | contract-tested only | contract-tested only | crash/restart fixture |
| process timeout/cancel | implemented | contract-tested only | contract-tested only | child-process and cancellation logs |
| FFmpeg/FFprobe discovery | supported-system or bundled | PoC pending | PoC pending | signed runtime fingerprint |
| Office rendering | PowerPoint/LibreOffice adapters upstream | LibreOffice PoC pending | LibreOffice PoC pending | 8-page and portrait MP4 hash |
| credentials | Windows store adapter boundary | Keychain adapter pending | Secret Service adapter pending | redaction and revoke evidence |
| installer/update | existing Windows packaging | notarized bundle pending | AppImage/package pending | install, upgrade, rollback, uninstall |

The capability snapshot must report `unsupported`, `missing`,
`misconfigured`, or `temporarily_unavailable`; it must never claim parity from
the Linux CI runner alone. B10 remains open until a clean macOS host and a
clean Linux host produce the real media artifacts described above. B11 remains
open until signed release runners provide installer evidence.
