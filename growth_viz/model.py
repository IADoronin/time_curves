"""Модель данных одного эксперимента."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class Sample:
    """Один эксперимент: имя, условия (meta) и временные ряды (data)."""

    name: str
    meta: dict[str, object]
    data: pd.DataFrame
    path: Path | None = None
    enabled: bool = True     # включён ли в текущую визуализацию
    time_shift: float = 0.0  # оценённый сдвиг «нуля» для выравнивания

    @property
    def value_columns(self) -> list[str]:
        """Колонки измеряемых величин (всё, кроме оси времени)."""
        return [c for c in self.data.columns if c != self.time_column]

    @property
    def time_column(self) -> str:
        """Имя колонки времени (первая колонка листа data)."""
        return self.data.columns[0]

    def raw_times(self) -> np.ndarray:
        """Исходные (записанные) моменты времени."""
        return self.data[self.time_column].to_numpy(dtype=float)

    def times(self) -> np.ndarray:
        """Моменты времени с учётом коррекции сдвига (для отрисовки)."""
        return self.raw_times() - self.time_shift

    def meta_value(self, key: str) -> object:
        """Значение условия по ключу (или None, если нет)."""
        return self.meta.get(key)
