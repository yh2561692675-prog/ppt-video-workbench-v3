"""Measure a command from spawn through a successful HTTP health response."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from workbench.performance.sampler import PerformanceSampler


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--temporary-root", type=Path, required=True)
    parser.add_argument("--health-url", required=True)
    parser.add_argument("--timeout", type=float, default=40.0)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--cwd", type=Path, default=Path("."))
    parser.add_argument("--command", nargs=argparse.REMAINDER, required=True)
    return parser


def _healthy(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:  # noqa: S310
            return int(response.status) == 200
    except (OSError, TimeoutError, urllib.error.HTTPError):
        return False


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.timeout <= 0:
        raise SystemExit("--timeout must be positive")
    if not args.command:
        raise SystemExit("--command must contain an executable")
    command = args.command[1:] if args.command[0] == "--" else args.command
    if not command:
        raise SystemExit("--command must contain an executable")
    process = subprocess.Popen(command, cwd=args.cwd.resolve())
    sampler = PerformanceSampler(
        args.output,
        # The helper itself is not a product component and must not become a
        # root: it is the API process' parent, so including it would attribute
        # all API descendants to an artificial ``probe`` component. Production
        # launcher runs can supply their real launcher root via the lower-level
        # sampler.
        {"api": process.pid},
        temporary_root=args.temporary_root,
        interval_seconds=args.interval,
    )
    sampler.start()
    sampler.record_stage("startup_to_health", "started")
    started = time.monotonic()
    health_elapsed_ms: int | None = None
    healthy = False
    try:
        while time.monotonic() - started < args.timeout:
            if process.poll() is not None:
                break
            if _healthy(args.health_url):
                healthy = True
                health_elapsed_ms = round((time.monotonic() - started) * 1000)
                break
            time.sleep(0.1)
    finally:
        # A completed stage boundary is emitted for both the passing and the
        # timeout/process-exit paths.  The verdict below remains fail-closed.
        sampler.record_stage("startup_to_health", "finished")
        # Keep the monitored process alive long enough to produce an interval
        # sample, while the stage duration remains the actual health latency.
        time.sleep(args.interval)
        summary = sampler.stop()
        _terminate(process)
    print(
        json.dumps(
            {
                "status": "passed" if healthy else "failed",
                "health_url": args.health_url,
                "health_elapsed_ms": health_elapsed_ms,
                "summary": str(summary),
                "events": str(sampler.events_path),
            },
            ensure_ascii=False,
        )
    )
    return 0 if healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
