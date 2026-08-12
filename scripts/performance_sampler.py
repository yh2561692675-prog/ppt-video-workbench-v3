"""Run the DP40 resource sampler against named launcher/API/worker roots."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from workbench.performance.sampler import PerformanceSampler


def _root(value: str) -> tuple[str, int]:
    name, separator, raw_pid = value.partition("=")
    if not separator or not name.strip():
        raise argparse.ArgumentTypeError("root must use name=pid")
    try:
        pid = int(raw_pid)
    except ValueError as error:
        raise argparse.ArgumentTypeError("root pid must be an integer") from error
    if pid <= 0:
        raise argparse.ArgumentTypeError("root pid must be positive")
    return name.strip(), pid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="ignored evidence output directory"
    )
    parser.add_argument(
        "--temporary-root", type=Path, required=True, help="render temporary directory"
    )
    parser.add_argument(
        "--root", type=_root, action="append", required=True, help="role=pid; repeatable"
    )
    parser.add_argument(
        "--interval", type=float, default=1.0, help="sampling interval, 1-5 seconds"
    )
    parser.add_argument(
        "--duration", type=float, required=True, help="collection duration in seconds"
    )
    parser.add_argument("--stage", default="acceptance", help="initial phase name")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.duration <= 0:
        raise SystemExit("--duration must be positive")
    roots = dict(args.root)
    if len(roots) != len(args.root):
        raise SystemExit("root names must be unique")
    sampler = PerformanceSampler(
        args.output,
        roots,
        temporary_root=args.temporary_root,
        interval_seconds=args.interval,
    )
    sampler.start()
    sampler.record_stage(args.stage, "started")
    try:
        time.sleep(args.duration)
    except KeyboardInterrupt:
        pass
    finally:
        sampler.record_stage(args.stage, "finished")
        print(sampler.stop())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
