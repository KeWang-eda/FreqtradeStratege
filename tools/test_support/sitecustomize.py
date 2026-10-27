"""Opt-in call observer, inherited by Python children of the test runner.

Wrappers call the original implementations with identical arguments. No model,
feature, data or acceptance result is substituted. Counts distinguish attempts,
normal returns and exceptions. Only original repository data paths count as
market_file_reads; all other pandas reads have a separate counter.
"""

import atexit
import builtins
import collections
import functools
import json
import os
import resource
import subprocess
import sys
import threading
import time
from pathlib import Path

if os.environ.get("QUANT_TEST_PROFILE_DIR"):
    _started = time.monotonic()
    _counts = collections.Counter()
    _details = collections.Counter()
    _elapsed = collections.Counter()
    _lock = threading.RLock()
    _support = str(Path(__file__).resolve().parent)
    _directory = Path(os.environ["QUANT_TEST_PROFILE_DIR"])
    _repository = Path(__file__).resolve().parents[2]
    _directory.mkdir(parents=True, exist_ok=True)
    _patching = False

    def _wrap(owner, name, kind):
        original = getattr(owner, name, None)
        if original is None or getattr(original, "_quant_observer", False):
            return

        @functools.wraps(original)
        def observed(*args, **kwargs):
            current = kind
            source = ""
            if kind == "dataframe_reads":
                path = kwargs.get("path", args[0] if args else "")
                if isinstance(path, (str, os.PathLike)):
                    source = str(Path(path).resolve())
                    if Path(source).is_relative_to(_repository / "data"):
                        current = "market_file_reads"
            test = os.environ.get("PYTEST_CURRENT_TEST", "process/setup")
            key = (current, test, original.__module__ + "." + original.__qualname__, source)
            start = time.monotonic()
            with _lock:
                _counts[current] += 1
                _details[key] += 1
            try:
                result = original(*args, **kwargs)
            except BaseException:
                with _lock:
                    _counts[current + "_failed"] += 1
                raise
            else:
                with _lock:
                    _counts[current + "_completed"] += 1
                return result
            finally:
                with _lock:
                    _elapsed[current] += time.monotonic() - start

        observed._quant_observer = True
        setattr(owner, name, observed)

    def _patch():
        global _patching
        if _patching:
            return
        _patching = True
        try:
            targets = [
                ("pandas", None, "read_feather", "dataframe_reads"),
                ("pandas", None, "read_parquet", "dataframe_reads"),
                ("xgboost.sklearn", "XGBRegressor", "fit", "xgboost_fits"),
                (
                    "quant.validation.native_features",
                    None,
                    "populate_native_features",
                    "production_feature_expansions",
                ),
                (
                    "quant.validation.native_features",
                    None,
                    "audit_native_features",
                    "production_feature_audits",
                ),
                (
                    "quant.research.fold_training",
                    None,
                    "verify_development_folds",
                    "independent_verifications",
                ),
                (
                    "quant.research.controlled",
                    None,
                    "verify_controlled_research",
                    "independent_verifications",
                ),
                (
                    "tools.verify_native_training_acceptance",
                    None,
                    "verify_native_training_acceptance",
                    "independent_verifications",
                ),
            ]
            for hook in (
                "feature_engineering_expand_all",
                "feature_engineering_expand_basic",
                "feature_engineering_standard",
            ):
                targets.append(
                    (
                        "quant.execution.freqtrade_strategy",
                        "QuantStrategy",
                        hook,
                        "production_feature_hooks",
                    )
                )
            for module, owner, name, kind in targets:
                loaded = sys.modules.get(module)
                if loaded is not None:
                    target = getattr(loaded, owner, None) if owner else loaded
                    if target is not None:
                        _wrap(target, name, kind)
        finally:
            _patching = False

    _original_import = builtins.__import__

    def _observed_import(*args, **kwargs):
        result = _original_import(*args, **kwargs)
        _patch()
        return result

    builtins.__import__ = _observed_import
    _original_popen = subprocess.Popen

    class _ObservedPopen(_original_popen):
        def __init__(self, *args, **kwargs):
            env = dict(os.environ if kwargs.get("env") is None else kwargs["env"])
            entries = env.get("PYTHONPATH", "").split(os.pathsep)
            env["PYTHONPATH"] = os.pathsep.join([_support, *[p for p in entries if p != _support]])
            env.setdefault("QUANT_TEST_PROFILE_DIR", str(_directory))
            kwargs["env"] = env
            with _lock:
                _counts["subprocesses"] += 1
            super().__init__(*args, **kwargs)

    subprocess.Popen = _ObservedPopen
    _patch()

    def _save():
        usage = resource.getrusage(resource.RUSAGE_SELF)
        value = {
            "schema": "quant-test-profile-v2",
            "pid": os.getpid(),
            "argv": sys.argv,
            "completed_observer": True,
            "seconds": time.monotonic() - _started,
            "cpu_user_seconds": usage.ru_utime,
            "cpu_system_seconds": usage.ru_stime,
            "counts": dict(_counts),
            "inclusive_call_seconds": dict(_elapsed),
            "events": [
                {"kind": k[0], "test": k[1], "function": k[2], "source": k[3], "count": n}
                for k, n in sorted(_details.items())
            ],
        }
        (_directory / f"{os.getpid()}.json").write_text(json.dumps(value, indent=2) + "\n")

    atexit.register(_save)
