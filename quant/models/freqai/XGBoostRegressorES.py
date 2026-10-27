"""XGBoost 回归模型，带真正生效的早停。

FreqAI 自带的 XGBoostRegressor 在 xgboost >= 3.0 下早停失效：
它把 `early_stopping_rounds` 传给构造函数，而 xgboost 3.x 的
`XGBRegressor.__init__` 只接受 `objective` + `**kwargs`，该参数被静默丢弃；
`fit()` 也不接受 `early_stopping_rounds`。

实测（xgboost 3.4.1）：自带实现在 n_estimators=500 时跑满 500 轮，
早停从不触发；改用 `callbacks=[EarlyStopping(...)]` 后正常停止。

另外自带实现的 `eval_set` 顺序是 (test, train)，而 xgboost 的早停监控
**最后一个** eval_set，等于在监控训练集 —— 训练集 RMSE 单调下降，早停必然失效。
这里只传测试集，监控目标明确。

This FreqAI-discoverable adapter owns the framework training lifecycle. The
framework-independent XGBoost constructor lives in ``quant.models.estimators``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from time import time
from typing import TYPE_CHECKING, Any

import xgboost as xgb
from freqtrade.freqai.base_models.BaseRegressionModel import BaseRegressionModel
from freqtrade.freqai.tensorboard import TBCallback

from quant.errors import DataContractError
from quant.market_data.contracts import frame_fingerprint
from quant.models.estimators import create_estimator
from quant.training.native_isolation import (
    IdentityPreservingPipeline,
    bind_cache_contract,
    canonical_sha256,
    purge_native_split,
    training_contract,
    validate_native_config,
    validate_training_alignment,
    write_audit_artifacts,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen


class XGBoostRegressorES(BaseRegressionModel):
    """早停回归模型，在任何拟合前严格隔离未来标签并保护缓存。"""

    def __init__(self, config: dict) -> None:
        # This must precede super(): DataDrawer loads existing models/predictions there.
        self.native_cache_contract = bind_cache_contract(config)
        super().__init__(config)

    def define_data_pipeline(self, threads=-1):
        pipeline = super().define_data_pipeline(threads=threads)
        return IdentityPreservingPipeline(pipeline.steps, pipeline.fitparams)

    def define_label_pipeline(self, threads=-1):
        pipeline = super().define_label_pipeline(threads=threads)
        return IdentityPreservingPipeline(pipeline.steps, pipeline.fitparams)

    def train(self, unfiltered_df, pair: str, dk: FreqaiDataKitchen, **kwargs) -> Any:
        """FreqAI 2026.7 train lifecycle with pre-fit purge and indexed audits.

        Upstream BaseRegressionModel.train is a small, fixed-version lifecycle.
        Its fit() hook runs after fit_labels and both preprocessing fits, so that
        public hook alone cannot fix this bug. This local override retains the
        native filtering, split, transforms, model and callback semantics.
        """
        validate_native_config(self.config)
        if training_contract(self.config) != self.native_cache_contract:
            raise DataContractError(
                "Training input/cache contract changed since model initialization"
            )
        start_time = time()
        logger.info("-------------------- Starting isolated training %s --------------------", pair)
        features, labels = dk.filter_features(
            unfiltered_df, dk.training_features_list, dk.label_list, training_filter=True
        )
        dd = dk.make_train_test_datasets(features, labels)
        samples = purge_native_split(unfiltered_df, pair, dk, dd, self.config)
        validate_training_alignment(samples, dd)
        # Keep logical references reproducible across fresh userdirs. The actual
        # input and training contract determine identity; an existing run is
        # never overwritten or silently treated as successful cached training.
        audit_identity = canonical_sha256(
            {
                "pair": pair,
                "input_fingerprint": frame_fingerprint(
                    unfiltered_df[["date", *dk.training_features_list, *dk.label_list]]
                ),
                "training_contract_sha256": canonical_sha256(self.native_cache_contract),
            }
        )
        directory = Path(dk.data_path) / "native_training_audit" / audit_identity
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError as exc:
            raise DataContractError(
                "Native training audit already exists for this input and contract; "
                "use a fresh userdir or identifier instead of overwriting evidence"
            ) from exc
        dk.data["native_training_contract"] = self.native_cache_contract["training_contract"]
        dk.data["native_training_audit"] = directory.relative_to(dk.data_path).as_posix()
        self.last_native_audit_path = directory
        write_audit_artifacts(
            directory,
            samples,
            unfiltered_df,
            dd,
            dk,
            self.config,
            phase="before_preprocessing",
            contract=self.native_cache_contract,
        )
        try:
            # Purge above must precede *all* learned statistics, including label means.
            dk.fit_labels()
            dk.feature_pipeline = self.define_data_pipeline(threads=dk.thread_count)
            dk.label_pipeline = self.define_label_pipeline(threads=dk.thread_count)
            dd["train_features"], dd["train_labels"], dd["train_weights"] = (
                dk.feature_pipeline.fit_transform(
                    dd["train_features"], dd["train_labels"], dd["train_weights"]
                )
            )
            dd["train_labels"], _, _ = dk.label_pipeline.fit_transform(dd["train_labels"])
            validation = self.freqai_info["data_split_parameters"].get("test_size", 0.1) != 0
            if validation:
                dd["test_features"], dd["test_labels"], dd["test_weights"] = (
                    dk.feature_pipeline.transform(
                        dd["test_features"], dd["test_labels"], dd["test_weights"]
                    )
                )
                dd["test_labels"], _, _ = dk.label_pipeline.transform(dd["test_labels"])
                if dd["test_features"].empty:
                    raise DataContractError(
                        "Early-stopping validation is empty after preprocessing"
                    )
            validate_training_alignment(samples, dd, fitted=True, dk=dk)
            write_audit_artifacts(
                directory,
                samples,
                unfiltered_df,
                dd,
                dk,
                self.config,
                phase="preprocessed",
                contract=self.native_cache_contract,
            )
            logger.info(
                "Training model on %d features and %d purged-safe data points",
                len(dd["train_features"].columns),
                len(dd["train_features"]),
            )
            model = self.fit(dd, dk)
            write_audit_artifacts(
                directory,
                samples,
                unfiltered_df,
                dd,
                dk,
                self.config,
                phase="trained",
                contract=self.native_cache_contract,
            )
        except Exception as exc:
            write_audit_artifacts(
                directory,
                samples,
                unfiltered_df,
                dd,
                dk,
                self.config,
                phase="failed",
                contract=self.native_cache_contract,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        logger.info(
            "-------------------- Done isolated training %s (%.2f secs) --------------------",
            pair,
            time() - start_time,
        )
        return model

    def fit(self, data_dictionary: dict, dk: FreqaiDataKitchen, **kwargs) -> Any:
        """训练回归模型，用测试集早停并保留最优轮次的模型。"""
        X = data_dictionary["train_features"]
        y = data_dictionary["train_labels"]

        training_parameters = dict(self.model_training_parameters)
        # 该参数在 xgboost >= 3 不再是构造参数，改由 callbacks 表达；
        # 从字典里摘掉，避免透传给底层 XGBModel 时产生歧义。
        early_stopping_rounds = int(training_parameters.pop("early_stopping_rounds", 0))

        if self.freqai_info.get("data_split_parameters", {}).get("test_size", 0.1) == 0:
            eval_set = None
            eval_weights = None
        else:
            # 只传测试集：EarlyStopping 监控最后一个 eval_set，
            # 混入训练集会让早停盯着训练集（自带实现的问题）。
            eval_set = [(data_dictionary["test_features"], data_dictionary["test_labels"])]
            eval_weights = [data_dictionary["test_weights"]]

        sample_weight = data_dictionary["train_weights"]
        xgb_model = self.get_init_model(dk.pair)

        model = create_estimator("xgboost", training_parameters)

        callbacks: list = [TBCallback(dk.data_path)]
        if early_stopping_rounds > 0 and eval_set is not None:
            callbacks.append(
                xgb.callback.EarlyStopping(
                    rounds=early_stopping_rounds,
                    save_best=True,
                    metric_name=training_parameters.get("eval_metric", "rmse"),
                    data_name="validation_0",
                )
            )
            logger.info("%s: 早停已启用 rounds=%d（监控测试集）", dk.pair, early_stopping_rounds)

        model.set_params(callbacks=callbacks)
        model.fit(
            X=X,
            y=y,
            sample_weight=sample_weight,
            eval_set=eval_set,
            sample_weight_eval_set=eval_weights,
            xgb_model=xgb_model,
        )
        # 序列化前清空 callbacks
        model.set_params(callbacks=[])

        if early_stopping_rounds > 0 and eval_set is not None:
            best = getattr(model, "best_iteration", None)
            rounds = len(model.evals_result().get("validation_0", {}).get("rmse", []))
            logger.info("%s: 实际训练轮数=%s best_iteration=%s", dk.pair, rounds, best)

        return model
