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
    enabled: bool = True       # включён ли в текущую визуализацию
    time_shift: float = 0.0    # оценённый сдвиг «нуля» для выравнивания
    time_mode: str = "elapsed"  # ось времени: 'elapsed' (часы) | 'dates'

    @property
    def value_columns(self) -> list[str]:
        """Колонки измеряемых величин: числовые, кроме колонки времени."""
        return [
            c for c in self.data.columns
            if c != self.time_column and pd.api.types.is_numeric_dtype(self.data[c])
        ]

    @property
    def time_column(self) -> str:
        """Имя колонки времени (первая колонка листа data)."""
        return self.data.columns[0]

    @property
    def is_datetime_time(self) -> bool:
        """Колонка времени — абсолютная дата+время (а не число)."""
        return pd.api.types.is_datetime64_any_dtype(self.data[self.time_column])

    def _start(self, dt: pd.Series) -> pd.Timestamp:
        try:
            return pd.to_datetime(self.meta.get("start_date"))
        except (ValueError, TypeError):
            return dt.iloc[0]

    def raw_times(self) -> np.ndarray:
        """Исходные моменты времени в числовой форме согласно ``time_mode``.

        Для datetime-столбца: 'elapsed' — часы от start_date; 'dates' —
        matplotlib-числа дат. Для числового столбца — как есть.
        """
        col = self.data[self.time_column]
        if self.is_datetime_time:
            if self.time_mode == "dates":
                import matplotlib.dates as mdates
                return mdates.date2num(col.to_numpy())
            elapsed = (col - self._start(col)) / pd.Timedelta(hours=1)
            return np.asarray(elapsed, dtype=float)
        return col.to_numpy(dtype=float)

    def times(self) -> np.ndarray:
        """Моменты времени с учётом коррекции сдвига (для отрисовки)."""
        return self.raw_times() - self.time_shift

    def meta_value(self, key: str) -> object:
        """Значение условия по ключу (или None, если нет)."""
        return self.meta.get(key)
