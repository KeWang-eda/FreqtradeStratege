"""Run frozen three-pair development preparation with a deny-all network audit."""

import argparse
import json
import sys
from pathlib import Path

from quant.infrastructure.experiment_store import file_hash, write_json
from quant.research.controlled import prepare_controlled_research
from tools.audit_local_network import install_policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-c", "--config", action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--train-development", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Refusing to reuse or overwrite an existing controlled output directory")
    audit = {"policy": "deny-all", "http_requests": [], "socket_events": [], "process_events": []}
    install_policy("deny-all", audit)
    state = {}
    code = 2
    try:
        result = prepare_controlled_research(
            args.config,
            args.output,
            train_development=args.train_development,
            execution_state=state,
        )
        code = 0
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "scope": "development",
                    "formal_research_status": "BLOCKED",
                }
            )
        )
    except Exception as error:
        print(
            json.dumps({"status": "FAIL", "type": type(error).__name__, "reason": str(error)}),
            file=sys.stderr,
        )
        code = 2
    finally:
        audit["denied_operations"] = sum(
            not item["allowed"]
            for key in ("http_requests", "socket_events", "process_events")
            for item in audit[key]
        )
        if audit["denied_operations"]:
            code = 3
        audit["completed"] = code == 0
        audit["exit_code"] = code
        if state.get("output_owned"):
            write_json(args.output / "network.json", audit)
            run_path = args.output / "run.json"
            if run_path.is_file():
                run = json.loads(run_path.read_text())
                if code != 0 and run.get("status") == "PASS":
                    run.update(
                        status="FAIL",
                        error={
                            "type": "NetworkAuditRejected",
                            "message": "A denied network operation invalidated this development run",
                        },
                    )
                run["artifacts"]["network.json"] = file_hash(args.output / "network.json")
                write_json(run_path, run)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
