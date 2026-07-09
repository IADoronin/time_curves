"""Тест datetime-конвейера: запись → экспорт → визуализатор (часы/даты).

Запуск:  python tests/smoke_datetime.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from growth_viz import aggregate, group_samples, load_folder
from recorder.db import MeasuredVar, Property, RecordingDB

OUT = ROOT / "tmp" / "dt_pipeline"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    db_path = OUT / "exp.db"
    if db_path.exists():
        db_path.unlink()

    db = RecordingDB(db_path)
    db.replace_properties([Property("substrate", "enum", ["malate", "acetate"], None, 0)])
    db.replace_measured_vars([MeasuredVar("OD600", None, 0)])

    # 2 субстрата × 2 повтора, разные стартовые даты
    starts = {
        "malate": [datetime(2026, 7, 1, 9, 0), datetime(2026, 7, 1, 11, 30)],
        "acetate": [datetime(2026, 7, 2, 8, 0), datetime(2026, 7, 2, 10, 15)],
    }
    for sub, sts in starts.items():
        for rep, start in enumerate(sts, 1):
            cid = db.create_curve(f"{sub}_{rep}", {"substrate": sub},
                                  start_iso=start.isoformat(sep=" "))
            for h in (0, 4, 8, 12):
                db.add_point(cid, start + timedelta(hours=h), {"OD600": 0.1 * h})
    db.export_all(OUT)
    db.close()

    samples = load_folder(OUT)
    assert len(samples) == 4
    s0 = samples[0]
    assert s0.is_datetime_time
    assert s0.value_columns == ["OD600"]  # datetime-столбец не попал в величины
    print("[ok] загружено 4 datetime-образца, value_columns=['OD600']")

    # режим «часы»: у всех одинаковая относительная сетка 0..12
    for s in samples:
        s.time_mode = "elapsed"
        assert np.allclose(s.raw_times(), [0, 4, 8, 12]), s.raw_times()
    print("[ok] режим 'часы': относительная ось 0..12 у всех повторов")

    # усреднение в режиме «часы» работает (повторы накладываются)
    groups = group_samples(samples, "substrate")
    for g in groups:
        for s in g.samples:
            s.time_mode = "elapsed"
        agg = aggregate(g, "OD600")
        assert len(agg) == 4 and int(agg["n"].max()) == 2, agg
    print("[ok] режим 'часы': aggregate усредняет 2 повтора на общей оси")

    # режим «даты»: разные даты → числа различаются, но конечны
    for s in samples:
        s.time_mode = "dates"
    mal = next(s for s in samples if s.meta["substrate"] == "malate")
    ace = next(s for s in samples if s.meta["substrate"] == "acetate")
    assert np.all(np.isfinite(mal.raw_times()))
    assert ace.raw_times()[0] > mal.raw_times()[0]  # ацетат стартовал позже
    print("[ok] режим 'даты': абсолютные даты, ацетат позже малата")

    print("\nВсе проверки datetime-конвейера пройдены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
