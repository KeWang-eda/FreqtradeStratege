"""Unified research commands; Freqtrade retains ownership of trade execution."""

import argparse
import json
import logging
from dataclasses import asdict
from pathlib import Path

from quant_strategy.api import build_dataset, compare_experiments, load_config, run_experiment
from quant_strategy.backends import create_regressor
from quant_strategy.backends.freqai import FreqAIBackendAdapter
from quant_strategy.infrastructure.artifact_audit import check_artifacts
from quant_strategy.market_data import load_ohlcv


def main(argv: list[str] | None = None) -> int:
    """Run research tasks; return 0 on success and 2 for invalid requests."""
    parser = argparse.ArgumentParser(prog="quant-strategy")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "run", "dataset-build"):
        sub = subparsers.add_parser(
            command, aliases=["config-check"] if command == "validate" else []
        )
        sub.add_argument("-c", "--config", action="append", required=True)
        sub.add_argument("--set", dest="overrides", action="append", default=[])
        if command == "run":
            sub.add_argument("--output", default="/tmp/quant-strategy-artifacts")
            sub.add_argument("--experiment-id")
            sub.add_argument("--evaluate-final-holdout", action="store_true")
    compare = subparsers.add_parser("compare")
    compare.add_argument("experiments", nargs="+")
    for command in ("artifact-check", "leakage-check"):
        subparsers.add_parser(command).add_argument("path", type=Path)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    try:
        return _execute(args)
    except (ValueError, KeyError, TypeError, OSError, ImportError, NotImplementedError) as exc:
        logging.getLogger(__name__).error("%s: %s", type(exc).__name__, exc)
        return 2


def _execute(args: argparse.Namespace) -> int:
    if args.command == "compare":
        print(json.dumps(compare_experiments(args.experiments), ensure_ascii=False, indent=2))
        return 0
    if args.command in {"artifact-check", "leakage-check"}:
        report = check_artifacts(args.path)
        if args.command == "leakage-check":
            report["leakage"] = json.loads((args.path / "leakage_report.json").read_text())
            report["passed"] = report["leakage"]["passed"]
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["passed"] else 1
    config = load_config(args.config, args.overrides)
    if args.command in {"validate", "config-check"}:
        if config.model.backend == "standalone":
            create_regressor(config.model, config.seed)
        else:
            FreqAIBackendAdapter().describe_capabilities()
        print(json.dumps(asdict(config), ensure_ascii=False, indent=2))
    elif args.command == "dataset-build":
        dataset = build_dataset(
            {pair: load_ohlcv(path) for pair, path in config.data.items()}, config
        )
        print(
            json.dumps(
                {
                    "samples": len(dataset.X),
                    "feature_columns": list(dataset.X),
                    "quality": dataset.quality,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        output = run_experiment(
            config,
            args.output,
            experiment_id=args.experiment_id,
            evaluate_final_holdout=args.evaluate_final_holdout,
        )
        print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
