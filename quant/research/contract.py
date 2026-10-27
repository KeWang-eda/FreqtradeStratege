"""Freeze task semantics before evaluation, independently of production defaults.

References: repository labels/returns.py, installed FreqAI feature expansion,
and sklearn's train-only fitting guidance. Checksums provide local integrity,
not signatures or proof that historical holdout data was never observed.
"""

import json
from dataclasses import asdict
from pathlib import Path

from quant.config import ExperimentConfig, load_config
from quant.errors import DataContractError
from quant.infrastructure.experiment_store import canonical_hash, file_hash
from quant.validation.admission import admission_environment, read_evidence_json

PAIRS = ("BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT")
ROOT = Path(__file__).resolve().parents[2]


def load_research_contract(path: str | Path) -> dict:
    """Read a versioned, checksum-bound contract, refusing unbound manual edits."""
    path = Path(path)
    contract = read_evidence_json(path)
    checksum = path.with_suffix(path.suffix + ".sha256").read_text().split()[0]
    if file_hash(path) != checksum:
        raise DataContractError("Frozen research contract checksum mismatch")
    if contract.get("schema_version") != 1 or contract.get("scope") != "development":
        raise DataContractError("Only versioned development research contracts are supported")
    if contract.get("pairs") != list(PAIRS):
        raise DataContractError("Controlled research is restricted to BTC/ETH/BNB")
    if contract.get("formal_oos_allowed") is not False:
        raise DataContractError("This research contract cannot unlock formal OOS")
    for name, digest in contract["production_source_sha256"].items():
        if file_hash(ROOT / name) != digest:
            raise DataContractError("Production source/configuration changed after contract freeze")
    for record in contract["input_files"].values():
        if file_hash(ROOT / record["path"]) != record["sha256"]:
            raise DataContractError("Frozen research input changed")
    if contract["environment"] != admission_environment():
        raise DataContractError("Frozen contract dependency environment changed")
    return contract


def validate_research_equivalence(contract: dict, native: dict, research: ExperimentConfig) -> dict:
    """Require the exact production label/horizon and model parameter source."""
    label = contract["label"]
    horizon = native["freqai"]["feature_parameters"]["label_period_candles"]
    expected = {
        "mode": native["my_experiment"]["label"],
        "horizon_candles": horizon,
        "timeframe": native["timeframe"],
        "volatility_period": 14,
    }
    if any(label.get(key) != value for key, value in expected.items()):
        raise DataContractError("Contract label differs from production target semantics")
    if (
        native["timeframe"] != "4h"
        or horizon != 3
        or asdict(research.label)
        != {"mode": label["mode"], "prediction_horizon": 3, "volatility_period": 14}
        or research.timeframe != "4h"
    ):
        raise DataContractError("Research must preserve production volnorm/4h/horizon=3")
    if (
        research.model.backend != "freqai"
        or research.model.name != native["freqaimodel"]
        or research.model.params != native["freqai"]["model_training_parameters"]
        or contract["model"]["parameters"] != research.model.params
        or set(research.data) != set(PAIRS)
        or asdict(research.validation) != contract["validation"]
        or research.feature_version != contract["feature_version"]
        or list(research.periods)
        != native["freqai"]["feature_parameters"]["indicator_periods_candles"]
        or list(research.features) != native["my_experiment"]["features"]
        or research.seed != native["freqai"]["data_split_parameters"]["random_state"]
    ):
        raise DataContractError("Research model, data universe or validation differs from contract")
    for pair, path in research.data.items():
        if (
            Path(path).resolve()
            != (ROOT / contract["input_files"][pair + "|futures"]["path"]).resolve()
        ):
            raise DataContractError("Research data paths differ from the frozen contract")
    return {
        "status": "PASS",
        "label_equivalent": True,
        "model_parameters_equivalent": True,
        "research_feature_engine": "actual native per-pair expansion; not legacy 26-column research",
        "native_outer_schedule_equivalent": False,
        "outer_schedule_difference": "Explicit expanding WF development fixture versus native 365d/7d backtesting",
        "formal_oos_allowed": False,
    }


def resolve_controlled_configuration(paths: list[str]) -> tuple[ExperimentConfig, dict, dict]:
    """Resolve overlays in order and verify their mandatory dedicated contract."""
    research = load_config(paths)
    if not research.research_contract:
        raise DataContractError("Controlled native research requires research_contract")
    contract = load_research_contract(research.research_contract)
    if paths != [item["path"] for item in contract["research_config_files"]] or any(
        file_hash(item["path"]) != item["sha256"] for item in contract["research_config_files"]
    ):
        raise DataContractError("Research configuration files/order differ from frozen contract")
    native = json.loads((ROOT / "config.json").read_text())
    validate_research_equivalence(contract, native, research)
    return research, contract, native


def contract_identity(contract: dict) -> str:
    """Stable semantic identity, used in every sample and execution receipt."""
    return canonical_hash(contract)
