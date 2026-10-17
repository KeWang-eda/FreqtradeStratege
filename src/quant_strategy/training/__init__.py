"""Fold-local per-pair standalone training and auditable prediction results."""

from .trainer import StandaloneBackend, TrainingRequest, TrainingResult

__all__ = ["StandaloneBackend", "TrainingRequest", "TrainingResult"]
