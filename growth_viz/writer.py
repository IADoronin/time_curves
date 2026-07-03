"""Запись эксперимента в .xlsx (инверсия loader).

Формат полностью совпадает с тем, что читает :mod:`growth_viz.loader`:
лист ``meta`` (колонки parameter/value) и лист ``data`` (1-я колонка — время).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .loader import DATA_SHEET, META_SHEET


def write_sample(path: str | Path, meta: dict[str, object], data: pd.DataFrame) -> Path:
    """Сохранить один эксперимент в .xlsx.

    meta — словарь условий (в т.ч. ``sample_name``, ``start_date``); пишется как
    таблица parameter/value. data — временные ряды (первая колонка — время).
    Возвращает путь к записанному файлу.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta_df = pd.DataFrame(
        [(str(k), v) for k, v in meta.items()],
        columns=["parameter", "value"],
    )
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        meta_df.to_excel(xw, sheet_name=META_SHEET, index=False)
        data.to_excel(xw, sheet_name=DATA_SHEET, index=False)
    return path
