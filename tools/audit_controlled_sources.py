"""Read-only BTC/ETH/BNB source inventory and independently frozen cost assumptions."""

import argparse
import json
from pathlib import Path

from quant_strategy.infrastructure.experiment_store import file_hash, write_json
from quant_strategy.research.costs import build_cost_contract, validate_cost_scenario
from quant_strategy.research.governance import PAIRS, audit_three_pair_sources


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--pairs", nargs="+", default=list(PAIRS))
    parser.add_argument(
        "--output", type=Path, required=True, help="New evidence directory; never overwritten"
    )
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    before = file_hash(args.config)
    config = json.loads(args.config.read_text())
    report = audit_three_pair_sources(config, args.pairs)
    costs = build_cost_contract(config)
    scenarios = [validate_cost_scenario(costs, scenario) for scenario in costs["scenarios"]]
    if before != file_hash(args.config):
        raise RuntimeError("Production configuration changed during read-only audit")
    write_json(args.output / "sources.json", report)
    write_json(args.output / "cost_contract.json", costs)
    write_json(args.output / "cost_scenarios.json", scenarios)
    write_json(
        args.output / "artifacts.json",
        {path.name: file_hash(path) for path in sorted(args.output.iterdir()) if path.is_file()},
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "sources": len(report["sources"]),
                "prediction_source_status": {
                    item["pair"]: item["source_prediction_preparation_status"]
                    for item in report["per_pair"]
                },
                "trade_evaluation_status": costs["trade_evaluation_status"],
                "formal_research_allowed": False,
            }
        )
    )
    return 1 if report["status"] == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
