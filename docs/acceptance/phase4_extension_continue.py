"""Continue attempt 2 after correcting only the online syscall classifier."""
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from quant_strategy.infrastructure.experiment_store import file_hash
from tools.run_offline_extension import (
    CONFIGS,
    PAIRS,
    PREFIX,
    ROOT,
    finish_offline,
    inspect_online_trace,
    validate_gates,
    validate_online_audit,
)
from tools.run_offline_acceptance import check_isolation, json_text

workspace = Path(sys.argv[1]).resolve()
output = ROOT / "docs/acceptance"
minimum = output / "phase4_summary.json"
coverage = output / "phase3_extension_coverage.json"
validate_gates(minimum, coverage)
check_isolation()
audit = json.loads((workspace / f"{PREFIX}_online_network.json").read_text())
validate_online_audit(audit, workspace / "runs/online", audit["exit_code"])
execution = {
    "exit_code": audit["exit_code"],
    "audit": audit,
    "syscalls": inspect_online_trace((workspace / f"{PREFIX}_online_network.strace").read_text()),
    "provenance": "Fresh real online process from capture attempt 2; raw audit/log/syscalls revalidated after correcting only syscall classification, no online cache reuse or rerun",
}
original_data = {
    item["path"]: item["sha256"]
    for pair in json.loads(coverage.read_text())["pairs"]
    if pair["pair"] in PAIRS
    for item in pair["files"]
}
protected = [ROOT / config for config in CONFIGS]
protected.extend(ROOT.glob("*.py"))
protected.extend((ROOT / "src/quant_strategy").rglob("*.py"))
protected.extend((ROOT / "freqaimodels").glob("*.py"))
before = {str(path.relative_to(ROOT)): file_hash(path) for path in protected}
(workspace / f"{PREFIX}_input_manifest.json").write_text(json_text({
    "protected_sources": before,
    "history": original_data,
    "scope": "Source fingerprints recorded immediately before fresh offline continuation; history/config gate hashes predate online process",
    "recorded_at": datetime.now(UTC).isoformat(),
}))
finish_offline(
    workspace, output, minimum, coverage, execution, before, original_data, 2,
    source_guard_scope="Source fingerprints freeze before fresh offline continuation through finish; local history and base/local configs also match earlier Phase 3 gate",
)
print(json.dumps({"status": "PASS", "continuation": "attempt2 classifier correction, fresh offline training"}))
