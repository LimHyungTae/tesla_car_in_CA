"""Command-line entry point used by GitHub Actions."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from .monitor import run_monitor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Refresh Tesla Model Y CPO inventory safely")
    parser.add_argument("--force", action="store_true", help="Ignore the cadence gate")
    parser.add_argument("--now", help="Override current time with an ISO-8601 timestamp")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(os.environ.get("TESLA_MONITOR_ROOT", "."))
    result = run_monitor(root, force=args.force, now=args.now)
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True))
    if not result.success:
        print(
            f"WARNING: Tesla source refresh failed; preserved inventory is marked stale: {result.message}",
            file=sys.stderr,
        )
    # A controlled source failure is data, not a process failure: returning 0
    # lets Actions commit/deploy the degraded status. Configuration or storage
    # exceptions still escape and produce a non-zero process exit.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
