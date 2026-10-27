"""Backend capabilities distinguish independent training from FreqAI lifecycle."""

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class BackendCapabilities:
    """Only explicitly supported operations may be requested."""

    independent_splits: bool
    early_stopping: bool
    save_load: bool
    incremental_training: bool = False
    batch_prediction: bool = True


class TrainingBackend(Protocol):
    """High-level lifecycle contract; unsupported operations fail explicitly."""

    def describe_capabilities(self) -> BackendCapabilities:
        """Describe the backend's supported lifecycle operations."""
        ...

    def run_training(self, request: Any) -> Any:
        """Run a backend-specific, validated training request."""
        ...

    def predict(self, request: Any) -> Any:
        """Adapt predictions to the shared prediction contract."""
        ...
