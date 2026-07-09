"""Headless smoke-тест слоя записи: БД → экспорт .xlsx → чтение визуализатором.

Запуск:  python recorder/tests/smoke_recorder.py
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from growth_viz import load_sample
from recorder.db import DATETIME_COLUMN, MeasuredVar, Property, RecordingDB

OUT = ROOT / "tmp" / "recorder_test"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    db_path = OUT / "exp.db"
    if db_path.exists():
        db_path.unlink()

    db = RecordingDB(db_path)

    # схема: 1 enum + 1 numeric свойство, 2 измеряемые величины
    assert db.is_empty_schema()
    db.replace_properties([
        Property("substrate", "enum", ["malate", "acetate"], None, 0),
        Property("conc_mM", "numeric", None, "mM", 1, min_val=0.0, max_val=50.0),
    ])
    db.replace_measured_vars([MeasuredVar("OD600", None, 0), MeasuredVar("pH", None, 1)])
    props = db.list_properties()
    assert [p.name for p in props] == ["substrate", "conc_mM"]
    assert props[0].options == ["malate", "acetate"]
    assert props[1].min_val == 0.0 and props[1].max_val == 50.0
    assert not db.is_empty_schema()
    print("[ok] схема: поля + ограничения заданы")

    # кривая с meta
    cid = db.create_curve(
        "aero_malate_1", {"substrate": "malate", "conc_mM": 20.0},
        start_iso="2026-07-03 10:00:00",
    )

    # 3 точки с абсолютным временем (дата+время)
    db.add_point(cid, datetime(2026, 7, 3, 10, 0, 0), {"OD600": 0.02, "pH": 7.0})
    db.add_point(cid, datetime(2026, 7, 3, 12, 30, 0), {"OD600": 0.30, "pH": 6.9})
    db.add_point(cid, datetime(2026, 7, 3, 17, 15, 0), {"OD600": 0.90})  # pH пропущен
    assert db.last_ts(cid) == datetime(2026, 7, 3, 17, 15, 0)
    pts = db.list_points(cid)
    assert [p.ts.hour for p in pts] == [10, 12, 17]  # порядок по времени
    print("[ok] записано 3 точки с абсолютным временем")

    # флаги
    db.toggle_flag(cid, 0)
    db.toggle_flag(cid, 2)
    assert db.get_flags(cid) == 0b101
    assert db.get_curve(cid).flag_prefix() == "🔴🟢"
    db.toggle_flag(cid, 0)
    assert db.get_flags(cid) == 0b100
    print("[ok] флаги: toggle/маска/префикс работают")

    # экспорт и обратное чтение визуализатором
    path = db.export_curve(cid, OUT)
    s = load_sample(path)
    assert s.name == "aero_malate_1"
    assert s.meta["substrate"] == "malate" and "start_date" in s.meta
    assert s.time_column == DATETIME_COLUMN, s.time_column
    # столбец времени — настоящая дата
    assert pd.api.types.is_datetime64_any_dtype(s.data[DATETIME_COLUMN]), s.data.dtypes
    assert list(s.data["OD600"]) == [0.02, 0.30, 0.90]
    assert s.data["pH"].isna().tolist() == [False, False, True]
    print("[ok] round-trip: экспорт с datetime прочитан визуализатором")

    # вторая (пустая) кривая — для проверки батч-экспорта
    db.create_curve("aero_acetate_1", {"substrate": "acetate", "conc_mM": 20.0},
                    start_iso="2026-07-03 10:00:00")
    all_paths = db.export_all(OUT)
    assert len(all_paths) == 2
    nonempty = db.export_all(OUT, skip_empty=True)
    assert len(nonempty) == 1  # пустая пропущена
    print("[ok] батч-экспорт: export_all и skip_empty работают")

    db.close()
    print("\nВсе проверки записи пройдены. Файлы в", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
