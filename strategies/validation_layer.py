"""Experiment validation and promotion contract."""

from __future__ import annotations

from typing import Protocol

from contracts import ValidationReport


class ValidationLayer(Protocol):
    """Produce independent and combined experiment evidence."""

    def validate_experiment(self, experiment_id: str) -> ValidationReport:
        """Return a reproducible promotion decision."""
        ...


def validate_report(report: ValidationReport) -> None:
    """Validate a report before it is persisted."""
    if not report.experiment_id:
        raise ValueError("experiment_id must not be empty")
    if not report.parent_commit or not report.candidate_commit:
        raise ValueError("parent and candidate commits are required")
    if report.decision not in {"proposed", "running", "promoted", "rejected", "blocked"}:
        raise ValueError("unknown validation decision")
    if not report.reason:
        raise ValueError("validation report must include a reason")
