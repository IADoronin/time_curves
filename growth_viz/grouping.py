"""Группировка образцов по условию и усреднение повторов."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .model import Sample


@dataclass
class Group:
    """Группа образцов с общим значением условия группировки."""

    key: str            # имя условия, по которому группировали (напр. 'substrate')
    value: object       # значение условия (напр. 'malate')
    samples: list[Sample]

    @property
    def label(self) -> str:
        return f"{self.value}"


def group_samples(samples: list[Sample], key: str, only_enabled: bool = True) -> list[Group]:
    """Разбить образцы на группы по значению meta-поля ``key``.

    Порядок групп — по первому появлению значения.
    """
    groups: dict[object, Group] = {}
    for s in samples:
        if only_enabled and not s.enabled:
            continue
        val = s.meta_value(key)
        if val not in groups:
            groups[val] = Group(key=key, value=val, samples=[])
        groups[val].samples.append(s)
    return list(groups.values())


def aggregate(group: Group, value_col: str, only_enabled: bool = True) -> pd.DataFrame:
    """Усреднить один показатель по повторам группы на общей оси времени.

    Возвращает DataFrame с колонками: time, mean, std, n.
    Разные образцы могут иметь разные точки времени — они объединяются по
    общей оси, отсутствующие значения интерполируются внутри диапазона.
    """
    series = []
    for s in group.samples:
        if only_enabled and not s.enabled:
            continue
        if value_col not in s.data.columns:
            continue
        # используем скорректированное (выровненное) время
        ser = pd.Series(s.data[value_col].to_numpy(), index=s.times())
        ser = ser[~ser.index.duplicated(keep="first")].sort_index()
        series.append(ser)

    if not series:
        return pd.DataFrame(columns=["time", "mean", "std", "n"])

    # Общая ось времени = объединение всех точек.
    time_axis = np.unique(np.concatenate([s.index.to_numpy() for s in series]))

    aligned = []
    for ser in series:
        # Интерполяция только внутри диапазона образца (без экстраполяции).
        vals = np.interp(time_axis, ser.index.to_numpy(), ser.to_numpy(),
                         left=np.nan, right=np.nan)
        aligned.append(vals)

    mat = np.vstack(aligned)  # (n_samples, n_time)
    with np.errstate(invalid="ignore"):
        mean = np.nanmean(mat, axis=0)
        std = np.nanstd(mat, axis=0, ddof=0)
        n = np.sum(~np.isnan(mat), axis=0)

    return pd.DataFrame({"time": time_axis, "mean": mean, "std": std, "n": n})
