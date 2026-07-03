"""Мелкие помощники GUI: числовые поля с точкой-разделителем."""

from __future__ import annotations

from PyQt6.QtCore import QLocale
from PyQt6.QtGui import QDoubleValidator

# Локаль C: десятичный разделитель — точка, без группировки разрядов.
# Иначе при русской локали валидатор ждёт запятую и отклоняет «0.5».
_C_LOCALE = QLocale(QLocale.Language.C)


def double_validator(bottom: float | None = None,
                     top: float | None = None) -> QDoubleValidator:
    v = QDoubleValidator()
    v.setLocale(_C_LOCALE)
    v.setNotation(QDoubleValidator.Notation.StandardNotation)
    if bottom is not None:
        v.setBottom(bottom)
    if top is not None:
        v.setTop(top)
    return v


def parse_float(text: str) -> float:
    """Разобрать число, принимая и точку, и запятую как разделитель."""
    return float(text.strip().replace(",", "."))
