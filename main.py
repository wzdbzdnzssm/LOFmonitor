"""LOF premium monitor entrypoint."""

from __future__ import annotations

import argparse
import logging
import sys

from lofmonitor.scheduler import run_once, start_scheduler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A-share LOF premium monitor")
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (default: ./config.yaml)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Fetch data and push once")
    run_parser.add_argument(
        "--force",
        action="store_true",
        help="Run even on non-trading days",
    )

    subparsers.add_parser("schedule", help="Start daily scheduler at 14:30")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        run_once(args.config, force=args.force)
        return 0

    if args.command == "schedule":
        start_scheduler(args.config)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
