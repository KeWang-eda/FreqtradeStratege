"""Summarize measured pytest cost profiles without inferring research readiness."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

from quant.infrastructure.experiment_store import file_hash, write_json


def read_run(path: Path) -> dict:
    receipt = json.loads((path / "test_run.json").read_text())
    if receipt["exit_code"] or receipt["collect_only"]:
        raise ValueError("Only successfully executed runs may be compared")
    counts, events, times = Counter(), Counter(), Counter()
    cpu_user = cpu_system = 0.0
    profiles = receipt["profile_files_sha256"]
    if not profiles:
        raise ValueError("Missing actual profiling evidence")
    for filename, digest in profiles.items():
        profile = Path(filename)
        if file_hash(profile) != digest:
            raise ValueError("Profile changed after receipt")
        value = json.loads(profile.read_text())
        if value["schema"] != "quant-test-profile-v2" or not value["completed_observer"]:
            raise ValueError("Incomplete or incompatible profiler")
        counts.update(value["counts"])
        times.update(value["inclusive_call_seconds"])
        cpu_user += value["cpu_user_seconds"]
        cpu_system += value["cpu_system_seconds"]
        for event in value["events"]:
            events[(event["kind"], event["test"], event["function"])] += event["count"]
    cases = list(ET.parse(path / receipt["junit"]).getroot().iter("testcase"))
    slow = sorted([dict(c.attrib) for c in cases], key=lambda c: float(c["time"]), reverse=True)
    return {
        "exit_code": receipt["exit_code"],
        "counts": receipt["counts"],
        "seconds": receipt["duration_seconds"],
        "selected_nodes": len(receipt["selected_nodeids"]),
        "calls": dict(counts),
        "actual_pandas_implementation_read_calls": sum(
            n
            for (kind, _, function), n in events.items()
            if kind in {"market_file_reads", "dataframe_reads"}
            and (
                function.startswith("pandas.io.")
                or function in {"pandas.read_feather", "pandas.read_parquet"}
            )
        ),
        "inclusive_call_seconds": dict(times),
        "cpu_user_seconds_all_profiled_processes": cpu_user,
        "cpu_system_seconds_all_profiled_processes": cpu_system,
        "profiled_processes": len(profiles),
        "slowest20": slow[:20],
        "events": [
            {"kind": k[0], "test": k[1], "function": k[2], "count": n}
            for k, n in sorted(events.items())
        ],
        "receipt_sha256": file_hash(path / "test_run.json"),
        "observer_sha256": receipt["source_files_sha256"]["tools/test_support/sitecustomize.py"],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", type=Path, required=True)
    parser.add_argument("--after", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    before, after = read_run(args.before), read_run(args.after)
    if before["observer_sha256"] != after["observer_sha256"]:
        raise ValueError("Profiler definitions changed; counts are not comparable")
    call_names = set(before["calls"]) | set(after["calls"])
    result = {
        "scope": "test engineering cost, never prediction/trading effectiveness",
        "before": before,
        "after": after,
        "call_reductions": {
            k: before["calls"].get(k, 0) - after["calls"].get(k, 0) for k in sorted(call_names)
        },
        "seconds_reduction": before["seconds"] - after["seconds"],
        "definitions": {
            "market_file_reads": "Observed pandas read_feather/read_parquet entries at actual repository/data paths; attempted/completed/failed counted separately.",
            "production_feature_expansions": "Complete populate_native_features calls; individual feature hooks also reported separately.",
            "xgboost_fits": "Actual XGBRegressor.fit calls, with normal returns and exceptions distinguished; no mock fit substituted.",
            "independent_verifications": "Native/fold/controlled verifier calls, including negative fault injections; a normal return is not a PASS verdict.",
            "inclusive_call_seconds": "Nested calls overlap and must not be added as exclusive wall time.",
            "cpu": "Per-process self CPU sum, excluding profiler children double counting; no inference of physical disk service time.",
            "limits": "dataframe_reads includes instrumented test replacement wrappers; actual_pandas_implementation_read_calls filters original pandas read_feather/read_parquet implementations to remove those duplicate wrapper entries. Opt-in Python wrappers count loaded target functions in Python children/threads. Abruptly killed processes may lack an atexit receipt; OS syscall I/O, non-Python processes and uninstrumented alternate implementations are not inferred.",
        },
    }
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "before_calls": before["calls"],
                "after_calls": after["calls"],
                "seconds_reduction": result["seconds_reduction"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
