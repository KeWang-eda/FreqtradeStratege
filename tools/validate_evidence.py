"""Independently validate Funding and point-in-time universe evidence packages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from quant.research.evidence import validate_funding_package, validate_universe_package


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--funding", type=Path)
    parser.add_argument("--universe", type=Path)
    parser.add_argument("--pairs", nargs="+")
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument(
        "--mark-times",
        type=Path,
        help="JSON mapping instrument_id to exact UTC mark timestamps",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    if args.funding is None and args.universe is None:
        parser.error("at least one of --funding or --universe is required")
    report = {"funding": None, "universe": None}
    mark_times = None
    if args.mark_times is not None:
        mark_times = json.loads(args.mark_times.read_text(encoding="utf-8"))
    if args.funding is not None:
        report["funding"] = validate_funding_package(
            args.funding,
            pairs=args.pairs,
            start=args.start,
            end=args.end,
            mark_times=mark_times,
        )
    if args.universe is not None:
        report["universe"] = validate_universe_package(
            args.universe, pairs=args.pairs, start=args.start, end=args.end
        )
    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if all(item is None or item.get("status") == "PASS" for item in report.values()) else 2


if __name__ == "__main__":
    raise SystemExit(main())
