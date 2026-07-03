"""Коррекция сдвига времени между образцами (выравнивание кривых).

Каждый образец имеет неизвестный сдвиг «нуля» ε_s. Оцениваем его по опорному
показателю (ориентиру) и вычитаем: t' = t_записанное − ε_s. Привязка к среднему
положению ориентира сохраняет исходный диапазон оси времени.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from .model import Sample

THRESHOLD = "threshold"   # по уровню сигнала
MAX_RATE = "maxrate"      # по максимальной скорости изменения


def _crossing_time(t: np.ndarray, y: np.ndarray, level: float) -> float:
    """Время первого пересечения уровня ``level`` (линейная интерполяция)."""
    for i in range(len(y) - 1):
        y0, y1 = y[i], y[i + 1]
        lo, hi = (y0, y1) if y0 <= y1 else (y1, y0)
        if lo <= level <= hi and y1 != y0:
            frac = (level - y0) / (y1 - y0)
            return float(t[i] + frac * (t[i + 1] - t[i]))
    return np.nan


def _max_rate_time(t: np.ndarray, y: np.ndarray) -> float:
    """Время максимальной |скорости| изменения (середина крутейшего отрезка)."""
    if len(t) < 2:
        return np.nan
    dt = np.diff(t)
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = np.abs(np.diff(y) / dt)
    if not np.any(np.isfinite(slope)):
        return np.nan
    i = int(np.nanargmax(slope))
    return float(0.5 * (t[i] + t[i + 1]))


def _landmark(sample: Sample, ref_col: str, method: str, level: float) -> float:
    """Положение ориентира на исходной (несдвинутой) оси времени образца."""
    if ref_col not in sample.data.columns:
        return np.nan
    t = sample.raw_times()
    y = sample.data[ref_col].to_numpy(dtype=float)
    order = np.argsort(t)
    t, y = t[order], y[order]
    if method == THRESHOLD:
        return _crossing_time(t, y, level)
    return _max_rate_time(t, y)


def apply_alignment(
    samples: list[Sample],
    ref_col: str,
    method: str = THRESHOLD,
    level: float = 0.2,
    group_key: str | None = None,
    only_enabled: bool = True,
) -> dict[str, float]:
    """Оценить и проставить ``time_shift`` каждому образцу.

    Выравнивание выполняется **внутри каждой группы** (по ``group_key``): повторы
    приводятся к среднему положению ориентира своей группы, поэтому реальные
    различия между группами (напр. разный лаг у субстратов) сохраняются.

    Возвращает словарь {имя: ориентир} для диагностики. Образцы без валидного
    ориентира (не пересекли уровень и т.п.) получают сдвиг 0.
    """
    marks: dict[int, float] = {}
    buckets: dict[object, list[Sample]] = defaultdict(list)
    for s in samples:
        if only_enabled and not s.enabled:
            s.time_shift = 0.0
            continue
        marks[id(s)] = _landmark(s, ref_col, method, level)
        gval = s.meta_value(group_key) if group_key else None
        buckets[gval].append(s)

    result: dict[str, float] = {}
    for members in buckets.values():
        valid = [marks[id(s)] for s in members if np.isfinite(marks[id(s)])]
        if not valid:
            for s in members:
                s.time_shift = 0.0
            continue
        anchor = float(np.mean(valid))  # якорь группы = среднее положение ориентира
        for s in members:
            m = marks[id(s)]
            s.time_shift = (m - anchor) if np.isfinite(m) else 0.0
            result[s.name] = m
    return result


def clear_alignment(samples: list[Sample]) -> None:
    """Сбросить коррекцию (вернуть исходное время)."""
    for s in samples:
        s.time_shift = 0.0
