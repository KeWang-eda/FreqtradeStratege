"""低方差控制模型：只用动量/RSI特征的 Ridge 回归。

用于研究，不改策略接口。训练后包装成带 predict() 的对象，FreqAI
BaseRegressionModel.predict() 可直接调用并正常保存/加载。
"""

import logging
from typing import Any

import numpy as np
from sklearn.linear_model import Ridge

from freqtrade.freqai.base_models.BaseRegressionModel import BaseRegressionModel
from freqtrade.freqai.data_kitchen import FreqaiDataKitchen

logger = logging.getLogger(__name__)


class SelectedFeatureRidge:
    """持久化 Ridge + 训练时选定的列索引。"""

    def __init__(self, model: Ridge, selected_indices: list[int]):
        self.model = model
        self.selected_indices = selected_indices

    def _select(self, features):
        """在 DataFrame 或 ndarray 中使用相同的训练列。"""
        if hasattr(features, "iloc"):
            return features.iloc[:, self.selected_indices]
        return features[:, self.selected_indices]

    def predict(self, features):
        """用训练时相同的动量/RSI列预测。"""
        return self.model.predict(self._select(features))


class MomentumRidgeRegressor(BaseRegressionModel):
    """只使用因果动量与 RSI 特征的低方差回归控制模型。"""

    def fit(self, data_dictionary: dict, dk: FreqaiDataKitchen, **kwargs) -> Any:
        """选择动量/RSI列训练 Ridge；没有匹配列时明确失败。"""
        feature_names = list(dk.training_features_list)
        selected_indices = [
            index for index, name in enumerate(feature_names)
            if "momentum" in name or "rsi" in name
        ]
        if not selected_indices:
            raise ValueError("training_features_list 中没有 momentum/rsi 特征")

        X = data_dictionary["train_features"]
        y = data_dictionary["train_labels"]
        training_parameters = dict(self.model_training_parameters)
        alpha = float(training_parameters.get("ridge_alpha", 10.0))

        if hasattr(X, "iloc"):
            selected_X = X.iloc[:, selected_indices]
        else:
            selected_X = X[:, selected_indices]

        model = Ridge(alpha=alpha)
        model.fit(selected_X, y, sample_weight=data_dictionary["train_weights"])
        logger.info(
            "%s: Ridge 使用 %d/%d 个 momentum/rsi 特征，alpha=%.4f",
            dk.pair, len(selected_indices), len(feature_names), alpha,
        )
        return SelectedFeatureRidge(model, selected_indices)
