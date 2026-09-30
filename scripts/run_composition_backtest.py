"""Official composition backtest runner for the layered framework.

Contract (research-only):
  - Inputs are precomputed OOS predictions plus local OHLCV/funding feathers.
  - The chain is composed from the repository layers only:
    selection -> portfolio -> risk -> execution -> wallet accounting.
  - No model training, no data download, no order submission, no network calls.
  - The wallet accounting mirrors the EXP-254 research convention (8-hour
    holding periods, round-trip costs, signed funding) so results are directly
    comparable across the script and pipeline paths.

Usage:
  python scripts/run_composition_backtest.py \
      --predictions /tmp/exp252-oos/predictions.csv \
      --output-dir /tmp/exp259-composition
"""

from __future__ import annotations

import argparse
import json
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

STRATEGY_DIR = Path(__file__).resolve().parent.parent / "strategies"
if str(STRATEGY_DIR) not in sys.path:
    sys.path.insert(0, str(STRATEGY_DIR))

from execution_layer import ExecutionConfiguration  # noqa: E402
from feature_layer import build_vtech_model_features  # noqa: E402
from portfolio_layer import PortfolioConfiguration  # noqa: E402
from strategy_layer_pipeline import (  # noqa: E402
    FRAMEWORK_VERSION,
    LayeredStrategyPipeline,
    StrategyRunContext,
)
from validation_layer import calculate_wallet_metrics  # noqa: E402

OOS_START = pd.Timestamp("2024-08-17 10:00", tz="UTC")
OOS_END = pd.Timestamp("2026-09-27 02:00", tz="UTC")
FEATURE_VERSION = "vtech-base72-plus-momentum6-plus-technical11-v1"
LABEL_VERSION = "adverse-risk-v1"
MODEL_IDENTIFIER = "exp251-per-pair-adverse-risk-v1"


def build_pair_frame(one_pair: str, prediction_frame: pd.DataFrame, data_root: Path) -> pd.DataFrame:
    """Rebuild one pair's candidates and attach its OOS prediction."""
    symbol = one_pair.split("/")[0]
    frame = pd.read_feather(data_root / f"{symbol}_USDT_USDT-1h-futures.feather")
    frame = frame.sort_values("date").reset_index(drop=True)
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    frame = frame[
        (frame["date"] >= OOS_START) & (frame["date"] < OOS_END)
    ].reset_index(drop=True)
    enriched = build_vtech_model_features(frame, include_technical_candidates=True)
    enriched["timestamp"] = enriched["date"]
    enriched["pair"] = one_pair
    enriched["direction"] = np.where(
        enriched["mom_score"] > 0,
        1,
        np.where(enriched["short_mom_score"] > 0, -1, 0),
    )
    enriched["expected_edge"] = np.where(
        enriched["direction"] > 0,
        enriched["mom_score"],
        enriched["short_mom_score"],
    )
    enriched["directional_return_8"] = (
        enriched["close"].shift(-8) / enriched["close"] - 1.0
    ) * enriched["direction"]
    result = enriched[enriched["direction"].ne(0)].copy()
    result["side"] = result["direction"].map({1: "long", -1: "short"})
    result["execution_cost"] = 0.0015
    result = result.merge(
        prediction_frame[["timestamp", "pair", "side", "prediction"]],
        on=["timestamp", "pair", "side"],
        how="inner",
    )
    result["predicted_adverse_risk"] = result["prediction"]
    result = result.dropna(
        subset=["expected_edge", "predicted_adverse_risk", "directional_return_8", "close"]
    )
    return result[
        [
            "timestamp",
            "pair",
            "side",
            "expected_edge",
            "predicted_adverse_risk",
            "execution_cost",
            "close",
            "directional_return_8",
        ]
    ].reset_index(drop=True)


def load_candidates(
    predictions_path: Path, data_root: Path, output_dir: Path, pairs: list[str]
) -> pd.DataFrame:
    """Build candidates once and cache them next to the run artifacts."""
    cache_path = output_dir / "candidates.parquet"
    if cache_path.exists():
        return pd.read_parquet(cache_path)
    predictions = pd.read_csv(predictions_path)
    predictions["timestamp"] = pd.to_datetime(predictions["timestamp"], utc=True)
    with ProcessPoolExecutor(max_workers=6) as executor:
        parts = list(
            executor.map(
                build_pair_frame,
                pairs,
                [predictions[predictions["pair"] == pair] for pair in pairs],
                [data_root] * len(pairs),
            )
        )
    candidates = pd.concat(parts, ignore_index=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    candidates.to_parquet(cache_path, index=False)
    return candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, default=Path("/tmp/exp252-oos/predictions.csv"))
    parser.add_argument("--config", type=Path, default=Path("/home/wangke/project/freqtrade/user_data/config-vtech-backtest.json"))
    parser.add_argument("--data-root", type=Path, default=Path("/home/wangke/project/freqtrade/user_data/data/binance/futures"))
    parser.add_argument("--output-dir", type=Path, default=Path("/tmp/exp259-composition"))
    parser.add_argument("--decision-stride", type=int, default=8)
    parser.add_argument("--top-k-per-side", type=int, default=3)
    parser.add_argument("--min-net-edge", type=float, default=0.0)
    parser.add_argument("--risk-penalty", type=float, default=0.5)
    parser.add_argument("--max-open-trades", type=int, default=3)
    parser.add_argument("--leverage", type=float, default=2.0)
    parser.add_argument("--fee", type=float, default=0.0005)
    parser.add_argument("--slippage", type=float, default=0.0002)
    parser.add_argument("--quantity-step", type=str, default="0.001")
    parser.add_argument("--limit", type=int, default=0, help="debug: only the first N decisions")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pairs = json.loads(args.config.read_text())["exchange"]["pair_whitelist"]
    candidates = load_candidates(args.predictions, args.data_root, args.output_dir, pairs)
    print("candidate rows:", len(candidates), flush=True)

    funding_by_pair: dict[str, pd.DataFrame] = {}
    for one_pair in pairs:
        symbol = one_pair.split("/")[0]
        funding = pd.read_feather(
            args.data_root / f"{symbol}_USDT_USDT-1h-funding_rate.feather"
        )
        funding["date"] = pd.to_datetime(funding["date"], utc=True)
        funding_by_pair[one_pair] = funding[["date", "open"]].rename(
            columns={"open": "funding_rate"}
        )

    decisions = sorted(candidates["timestamp"].unique())[:: args.decision_stride]
    if args.limit:
        decisions = decisions[: args.limit]
    print("decision timestamps:", len(decisions), flush=True)

    grouped = {timestamp: frame for timestamp, frame in candidates.groupby("timestamp")}
    pipeline = LayeredStrategyPipeline()
    portfolio_configuration = PortfolioConfiguration(
        leverage=args.leverage,
        risk_budget=0.02,
        stop_distance=0.15,
        max_open_trades=args.max_open_trades,
        max_side_exposure=0.5,
        liquidation_buffer=0.05,
    )
    execution_configuration = ExecutionConfiguration(
        order_type="limit",
        fee_rate=args.fee,
        slippage_rate=args.slippage,
        funding_rate=0.0,
        quantity_step=args.quantity_step,
        minimum_stake=0.0,
    )
    context = StrategyRunContext(
        experiment_id="EXP-259",
        parent_commit="efeb8fe",
        strategy_version=FRAMEWORK_VERSION,
        feature_version=FEATURE_VERSION,
        label_version=LABEL_VERSION,
        model_identifier=MODEL_IDENTIFIER,
        data_snapshot="local-feather-2026-09-27",
    )

    equity = 100.0
    wallet_rows: list[dict[str, object]] = [
        {"date": pd.Timestamp(decisions[0]) - pd.Timedelta(hours=8), "total_quote": equity}
    ]
    order_rows: list[dict[str, object]] = []
    risk_rejected_total = 0
    execution_rejected_total = 0
    for processed, raw_timestamp in enumerate(decisions, start=1):
        timestamp = pd.Timestamp(raw_timestamp)
        rows = grouped.get(timestamp)
        if rows is None or rows.empty:
            continue
        current_prices = dict(zip(rows["pair"], rows["close"]))
        returns_by_pair = dict(zip(rows["pair"], rows["directional_return_8"]))
        run_result = pipeline.run(
            context,
            {
                "candidate_frame": rows[
                    [
                        "timestamp",
                        "pair",
                        "side",
                        "expected_edge",
                        "predicted_adverse_risk",
                        "execution_cost",
                    ]
                ].copy(),
                "account_equity": equity,
                "current_prices": current_prices,
                "top_k_per_side": args.top_k_per_side,
                "minimum_net_edge": args.min_net_edge,
                "risk_penalty": args.risk_penalty,
                "portfolio_configuration": portfolio_configuration,
                "execution_configuration": execution_configuration,
            },
        )
        allowed_decisions = [d for d in run_result.risk_decisions if d.allowed]
        risk_rejected_total += len(run_result.risk_decisions) - len(allowed_decisions)
        execution_rejected_total += len(allowed_decisions) - len(run_result.order_plans)
        period_return = 0.0
        finish = timestamp + pd.Timedelta(hours=8)
        for plan in run_result.order_plans:
            stake_fraction = plan.stake_amount / equity
            funding = funding_by_pair[plan.pair]
            funding_sum = float(
                funding.loc[
                    (funding["date"] > timestamp) & (funding["date"] <= finish),
                    "funding_rate",
                ].sum()
            )
            side_sign = 1.0 if plan.side == "long" else -1.0
            gross = args.leverage * float(returns_by_pair[plan.pair])
            cost_per_stake = (
                2.0 * (plan.expected_fee + plan.expected_slippage) / plan.stake_amount
            )
            funding_per_stake = args.leverage * funding_sum * side_sign
            net_per_stake = gross - cost_per_stake - funding_per_stake
            period_return += stake_fraction * net_per_stake
            order_rows.append(
                {
                    "timestamp": timestamp,
                    "pair": plan.pair,
                    "side": plan.side,
                    "stake": plan.stake_amount,
                    "leverage": plan.leverage,
                    "gross": gross,
                    "cost_per_stake": cost_per_stake,
                    "funding_per_stake": funding_per_stake,
                    "net_per_stake": net_per_stake,
                }
            )
        equity *= 1.0 + period_return
        wallet_rows.append({"date": finish, "total_quote": equity})
        if processed % 500 == 0:
            print(f"processed {processed}/{len(decisions)} equity={equity:.4f}", flush=True)

    wallet = pd.DataFrame(wallet_rows)
    orders = pd.DataFrame(order_rows)
    metrics = calculate_wallet_metrics(wallet, periods_per_year=365.0 * 3.0)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    wallet.to_csv(args.output_dir / "wallet.csv", index=False)
    orders.to_csv(args.output_dir / "orders.csv", index=False)
    summary = {
        "experiment": "EXP-259",
        "decisions": len(decisions),
        "order_count": int(len(orders)),
        "risk_rejected": risk_rejected_total,
        "execution_rejected": execution_rejected_total,
        "final_equity": float(wallet["total_quote"].iloc[-1]),
        "return": float(wallet["total_quote"].iloc[-1] / 100.0 - 1.0),
        "wallet_sharpe": metrics.wallet_sharpe,
        "wallet_calmar": metrics.wallet_calmar,
        "max_relative_drawdown": metrics.max_relative_drawdown,
        "product": metrics.product,
        "observation_count": metrics.observation_count,
    }
    (args.output_dir / "metrics.json").write_text(json.dumps(summary, indent=2))
    print("composition backtest: PASS", flush=True)
    print(json.dumps(summary, indent=2), flush=True)
    if len(orders):
        print("orders by pair:", flush=True)
        print(
            orders.groupby("pair").size().sort_values(ascending=False).to_string(),
            flush=True,
        )


if __name__ == "__main__":
    main()
