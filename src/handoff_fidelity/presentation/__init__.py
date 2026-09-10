"""Presentation, visualization, and manuscript sanitation contracts."""

from __future__ import annotations

from .figure_validator import FigureValidationResult, validate_figure, validate_figures_directory
from .sanitizer import SanitizationResult, SanitizationViolation, sanitize_file, sanitize_text

__all__ = [
    "FigureValidationResult",
    "SanitizationResult",
    "SanitizationViolation",
    "sanitize_file",
    "sanitize_text",
    "validate_figure",
    "validate_figures_directory",
]
