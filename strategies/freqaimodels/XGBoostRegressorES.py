"""XGBoostRegressor 早停修复版(官方 API 组合, 无自定义逻辑).

问题根因(2026-09-02 实测确诊):
- freqtrade/freqai/prediction_models/XGBoostRegressor.py 官方 fit 传双 eval_set:
    eval_set = [(test), (train)]                    # L39
- xgboost 3.4.x 的 EarlyStopping callback 默认监控**最后一个** eval_set(validation_1 = 训练集)
- 训练集误差随轮数持续下降 → 早停永不触发 → 训满 400 轮 → 严重过拟合
  (v7/v8 实测: 测试误差从轮11的0.049一路恶化到轮399的0.082, 模型在背答案)

修复(全部为官方 API):
- eval_set 只传 test 集 → EarlyStopping 默认监控最后(唯一)的 eval_set = test
- early_stopping_rounds=50(从 config model_training_parameters 读取, 未设时默认 50)
- xgboost 官方 predict() 会自动使用 best_iteration(最优树数), 不需要额外逻辑

实现参考:
- https://xgboost.readthedocs.io/en/stable/python/python_api.html
- freqtrade/freqai/prediction_models/XGBoostRegressor.py
- freqtrade/freqai/base_models/BaseRegressionModel.py
"""
import logging

from xgboost import XGBRegressor

from freqtrade.freqai.base_models.BaseRegressionModel import BaseRegressionModel
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
from freqtrade.freqai.tensorboard import TBCallback

logger = logging.getLogger(__name__)


class XGBoostRegressorES(BaseRegressionModel):
    """XGBoost 回归 + early stopping(监控验证集=test)."""

    def fit(self, data_dictionary: dict, dk: FreqaiDataKitchen, **kwargs):
        X = data_dictionary["train_features"]
        y = data_dictionary["train_labels"]

        if self.freqai_info.get("data_split_parameters", {}).get("test_size", 0.1) == 0:
            eval_set = None
            eval_weights = None
        else:
            # 只传 test 集: xgboost EarlyStopping 默认监控最后一个 eval_set,
            # 单 eval_set 时监控的就是 test, 防止盯着训练集永不早停(过拟合根因)
            eval_set = [(data_dictionary["test_features"], data_dictionary["test_labels"])]
            eval_weights = [data_dictionary["test_weights"]]

        sample_weight = data_dictionary["train_weights"]

        xgb_model = self.get_init_model(dk.pair)

        # 每个币都会调用 fit；复制参数，避免 pop() 让后续币丢失配置值。
        model_parameters = self.model_training_parameters.copy()
        early_stopping_rounds = model_parameters.pop("early_stopping_rounds", 50)
        if eval_set is None:
            model = XGBRegressor(**model_parameters)
        else:
            model = XGBRegressor(
                **model_parameters,
                early_stopping_rounds=early_stopping_rounds,
            )

        model.set_params(callbacks=[TBCallback(dk.data_path)])
        model.fit(
            X=X,
            y=y,
            sample_weight=sample_weight,
            eval_set=eval_set,
            sample_weight_eval_set=eval_weights,
            xgb_model=xgb_model,
            verbose=False,
        )
        if eval_set is not None:
            logger.info(
                "XGBoost validation best_iteration=%s best_score=%s",
                model.best_iteration,
                model.best_score,
            )
        model.set_params(callbacks=[])

        return model
