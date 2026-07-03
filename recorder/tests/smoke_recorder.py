"""Headless smoke-тест слоя записи: БД → экспорт .xlsx → чтение визуализатором.

Запуск:  python recorder/tests/smoke_recorder.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from growth_viz import load_sample
from recorder.db import MeasuredVar, Property, RecordingDB

OUT = ROOT / "tmp" / "recorder_test"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    db_path = OUT / "exp.db"
    if db_path.exists():
        db_path.unlink()

    db = RecordingDB(db_path)
    db.time_unit = "h"

    # схема: 1 enum + 1 numeric свойство, 2 измеряемые величины
    db.replace_properties([
        Property("substrate", "enum", ["malate", "acetate"], None, 0),
        Property("conc_mM", "numeric", None, "mM", 1),
    ])
    db.replace_measured_vars([
        MeasuredVar("OD600", None, 0),
        MeasuredVar("pH", None, 1),
    ])
    assert [p.name for p in db.list_properties()] == ["substrate", "conc_mM"]
    assert db.measured_names() == ["OD600", "pH"]
    print("[ok] схема: свойства + измеряемые величины заданы")

    # кривая с meta
    cid = db.create_curve(
        "aero_malate_1",
        {"substrate": "malate", "conc_mM": 20.0},
        start_iso="2026-07-03 10:00:00",
    )

    # 3 точки; последняя — «текущее время» (elapsed от старта)
    db.add_point(cid, 0.0, {"OD600": 0.02, "pH": 7.0})
    db.add_point(cid, 2.5, {"OD600": 0.30, "pH": 6.9})
    t_now = db.elapsed_since_start(cid)  # часы от 2026-07-03 10:00 до сейчас
    db.add_point(cid, t_now, {"OD600": 0.90})  # pH пропущен -> NaN
    assert db.last_time(cid) == t_now
    print(f"[ok] записано 3 точки (последняя 'сейчас' = {t_now:.2f} ч)")

    # экспорт и обратное чтение визуализатором
    path = db.export_curve(cid, OUT)
    s = load_sample(path)
    assert s.name == "aero_malate_1", s.name
    assert s.meta["substrate"] == "malate"
    assert float(s.meta["conc_mM"]) == 20.0
    assert "sample_name" in s.meta and "start_date" in s.meta
    assert s.time_column == "time_h", s.time_column
    assert s.value_columns == ["OD600", "pH"], s.value_columns
    assert list(s.data["OD600"]) == [0.02, 0.30, 0.90]
    # пропущенный pH в 3-й точке -> NaN
    assert s.data["pH"].isna().tolist() == [False, False, True]
    print("[ok] round-trip: экспорт прочитан визуализатором, значения совпали")

    # экспорт всех
    paths = db.export_all(OUT)
    assert len(paths) == 1 and paths[0].exists()
    print("[ok] export_all работает")

    db.close()
    print("\nВсе проверки записи пройдены. Файлы в", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
