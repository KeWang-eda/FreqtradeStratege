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
    for command in ("validate", "run", "formal-run", "dataset-build"):
        sub = subparsers.add_parser(
            command,
            aliases=["config-check"] if command == "validate" else [],
            help="Development training; never formal OOS admission"
            if command == "run"
            else "Formal research requires current independently verified admission"
            if command == "formal-run"
            else None,
        )
        sub.add_argument("-c", "--config", action="append", required=True)
        sub.add_argument("--set", dest="overrides", action="append", default=[])
        if command in {"run", "formal-run"}:
            sub.add_argument("--output", default="/tmp/quant-strategy-artifacts")
            sub.add_argument("--experiment-id")
            sub.add_argument("--evaluate-final-holdout", action="store_true")
        if command == "formal-run":
            sub.add_argument(
                "--readiness",
                type=Path,
                required=True,
                help="Current six-stage readiness.json; FAIL/PARTIAL/BLOCKED deny training",
            )
    compare = subparsers.add_parser("compare")
    compare.add_argument("experiments", nargs="+")
    controlled = subparsers.add_parser(
        "controlled-research",
        help="Frozen three-pair development preparation; formal holdout stays locked",
    )
    controlled.add_argument("-c", "--config", action="append", required=True)
    controlled.add_argument("--output", type=Path, required=True)
    controlled.add_argument("--train-development", action="store_true")
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
    if args.command == "controlled-research":
        from tools.prepare_controlled_research import main as controlled_main

        arguments = [value for path in args.config for value in ("-c", path)]
        arguments += ["--output", str(args.output)]
        if args.train_development:
            arguments.append("--train-development")
        return controlled_main(arguments)
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
    if args.command == "formal-run":
        from quant_strategy.validation.admission import require_training_admission

        require_training_admission(args.readiness, config)
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
            experiment_scope="formal" if args.command == "formal-run" else "development",
            readiness_path=args.readiness if args.command == "formal-run" else None,
        )
        print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
