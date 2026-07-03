"""Загрузка экспериментов из Excel-файлов.

Каждый .xlsx содержит лист ``meta`` (таблица parameter/value с условиями)
и лист ``data`` (временные ряды измеряемых величин).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .model import Sample

META_SHEET = "meta"
DATA_SHEET = "data"


def _meta_to_dict(meta_df: pd.DataFrame) -> dict[str, object]:
    """Преобразовать лист meta (parameter/value) в словарь.

    Устойчиво к регистру и лишним пробелам в заголовках.
    """
    cols = {c.strip().lower(): c for c in meta_df.columns}
    if "parameter" in cols and "value" in cols:
        keys = meta_df[cols["parameter"]].astype(str).str.strip()
        vals = meta_df[cols["value"]]
        return dict(zip(keys, vals))
    # Фолбэк: один ряд с именованными колонками -> условия.
    if len(meta_df) == 1:
        return {str(k).strip(): v for k, v in meta_df.iloc[0].items()}
    raise ValueError("Лист 'meta' должен иметь колонки parameter/value")


def load_sample(path: str | Path) -> Sample:
    """Загрузить один эксперимент из .xlsx."""
    path = Path(path)
    sheets = pd.read_excel(path, sheet_name=[META_SHEET, DATA_SHEET])
    meta = _meta_to_dict(sheets[META_SHEET])
    data = sheets[DATA_SHEET]
    name = str(meta.get("sample_name") or path.stem)
    return Sample(name=name, meta=meta, data=data, path=path)


def load_folder(folder: str | Path, pattern: str = "*.xlsx") -> list[Sample]:
    """Загрузить все .xlsx из папки. Битые файлы пропускаются с предупреждением."""
    folder = Path(folder)
    samples: list[Sample] = []
    for p in sorted(folder.glob(pattern)):
        if p.name.startswith("~$"):  # временные файлы Excel
            continue
        try:
            samples.append(load_sample(p))
        except Exception as exc:  # noqa: BLE001 — сообщаем и продолжаем
            print(f"[warn] пропущен {p.name}: {exc}")
    return samples


def common_meta_keys(samples: list[Sample]) -> list[str]:
    """Ключи meta, присутствующие во всех образцах (кандидаты для группировки)."""
    if not samples:
        return []
    keys = set(samples[0].meta)
    for s in samples[1:]:
        keys &= set(s.meta)
    # Технические поля не годятся для группировки.
    skip = {"sample_name", "start_date", "replicate"}
    return [k for k in samples[0].meta if k in keys and k not in skip]
