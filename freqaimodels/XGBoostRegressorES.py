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
"""

import logging
from typing import Any

import xgboost as xgb
from xgboost import XGBRegressor

from freqtrade.freqai.base_models.BaseRegressionModel import BaseRegressionModel
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
from freqtrade.freqai.tensorboard import TBCallback

logger = logging.getLogger(__name__)


class XGBoostRegressorES(BaseRegressionModel):
    """回归模型；与自带实现的唯一差别是早停真正生效。"""

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

        model = XGBRegressor(**training_parameters)

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
            logger.info(
                "%s: 早停已启用 rounds=%d（监控测试集）", dk.pair, early_stopping_rounds
            )

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
            logger.info(
                "%s: 实际训练轮数=%s best_iteration=%s", dk.pair, rounds, best
            )

        return model
