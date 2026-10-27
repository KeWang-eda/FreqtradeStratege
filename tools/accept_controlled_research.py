"""Independently verify controlled preparation; never grant formal OOS admission."""

import argparse
import json
from pathlib import Path

from quant.research.controlled import verify_controlled_research


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--test-run", type=Path, required=True)
    args = parser.parse_args()
    report = verify_controlled_research(args.evidence, args.output, args.test_run)
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("engineering_status", "status", "formal_research_allowed")
            }
        )
    )
    return 1 if report["status"] == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
