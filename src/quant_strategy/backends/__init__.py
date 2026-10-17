"""Model registry and adapters; imports do not initialize Freqtrade."""

from .factory import create_regressor

__all__ = ["create_regressor"]
