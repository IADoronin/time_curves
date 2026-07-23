"""Headless GUI-тест окна записи (QT_QPA_PLATFORM=offscreen).

Прогоняет логику окна без модальных диалогов: схема и кривые задаются через БД,
а ввод точек/таблица/флаги/удаление/экспорт — через методы окна.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication

from growth_viz import load_sample
from recorder.db import DATETIME_COLUMN, MeasuredVar, Property, RecordingDB
from recorder.record_window import RecordWindow

OUT = ROOT / "tmp" / "recorder_gui"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    db_path = OUT / "exp.db"
    if db_path.exists():
        db_path.unlink()

    app = QApplication(sys.argv)
    db = RecordingDB(db_path)
    db.replace_properties([Property("substrate", "enum", ["malate", "acetate"], None, 0)])
    db.replace_measured_vars([MeasuredVar("OD600", None, 0), MeasuredVar("pH", None, 1)])

    win = RecordWindow(db)
    assert set(win._value_edits) == {"OD600", "pH"}, list(win._value_edits)

    cid = db.create_curve("aero_malate_1", {"substrate": "malate"},
                          start_iso="2026-07-04 10:00:00")
    win._reload_curves()
    win._select_curve_id(cid)
    assert win._current_curve_id() == cid

    # добавление точки датой+временем; Enter в поле значения тоже добавляет
    win.dt_time.setValue(datetime(2026, 7, 4, 10, 0, 0))
    win._value_edits["OD600"].setText("0.02")
    win._value_edits["pH"].setText("7.0")
    win._add_point()
    win.dt_time.setValue(datetime(2026, 7, 4, 12, 30, 0))
    win._value_edits["OD600"].setText("0.5")
    win._value_edits["OD600"].returnPressed.emit()   # Enter добавляет точку
    assert len(db.list_points(cid)) == 2
    print("[ok] точки добавлены (дата+время; Enter добавляет)")

    # таб-порядок: дата → первое поле значения
    assert win.dt_time.edit.nextInFocusChain() is win._value_edits["OD600"] \
        or win._value_edits["OD600"] in [win.dt_time.edit.nextInFocusChain()]
    # «Сейчас» ставит текущую дату
    win._fill_now()
    assert win.dt_time.value().date() == datetime.now().date()
    print("[ok] 'Сейчас' ставит дату; таб-порядок дата→значения")

    # таблица точек
    assert win.points_table.columnCount() == 3
    assert win.points_table.horizontalHeaderItem(0).text() == "дата/время"
    assert win.points_table.rowCount() == 2
    print("[ok] таблица точек (дата/время, OD600, pH)")

    # удаление точки (выбрать строку 0 и удалить)
    win.points_table.selectRow(0)
    win._delete_points()
    assert len(db.list_points(cid)) == 1
    print("[ok] удаление выбранной точки")

    # флаги: toggle через окно → префикс в списке
    win._toggle_flag(cid, 2)  # 🟢
    assert "🟢" in win.curve_list.item(0).text()
    print("[ok] флаг выставлен и виден в списке")

    # экспорт: datetime-столбец читается визуализатором
    path = db.export_curve(cid, OUT)
    s = load_sample(path)
    assert s.time_column == DATETIME_COLUMN
    assert s.value_columns == ["OD600", "pH"]
    print("[ok] экспорт с datetime прочитан визуализатором")

    # батч-экспорт выбранных (выбрать все → export_curves)
    db.create_curve("aero_acetate_1", {"substrate": "acetate"},
                    start_iso="2026-07-04 10:00:00")
    win._reload_curves()
    ids = [c.id for c in db.list_curves()]
    paths = db.export_curves(ids, OUT)
    assert len(paths) == 2
    print("[ok] батч-экспорт выбранных кривых")

    # удаление кривой из БД (логика _delete_curves использует delete_curve)
    db.delete_curve(cid)
    assert len(db.list_curves()) == 1
    print("[ok] удаление кривой")

    db.close()
    print("\nВсе GUI-проверки записи пройдены. Файлы в", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
