"""Lifecycle adapters for standalone training and FreqAI."""

from .freqai import FreqAIBackendAdapter
from .standalone import StandaloneBackend

__all__ = ["FreqAIBackendAdapter", "StandaloneBackend"]
