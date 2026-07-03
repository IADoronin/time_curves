"""Headless GUI-тест окна записи (QT_QPA_PLATFORM=offscreen).

Прогоняет логику окна без модальных диалогов: схема и кривые задаются через БД,
а ввод точек/таблица/экспорт — через методы окна.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication

from growth_viz import load_sample
from recorder.db import MeasuredVar, Property, RecordingDB
from recorder.record_window import RecordWindow

OUT = ROOT / "tmp" / "recorder_gui"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    db_path = OUT / "exp.db"
    if db_path.exists():
        db_path.unlink()

    app = QApplication(sys.argv)
    db = RecordingDB(db_path)
    db.time_unit = "min"
    db.replace_properties([Property("substrate", "enum", ["malate", "acetate"], None, 0)])
    db.replace_measured_vars([MeasuredVar("OD600", None, 0), MeasuredVar("pH", None, 1)])

    win = RecordWindow(db)

    # поля значений построены по схеме
    assert set(win._value_edits) == {"OD600", "pH"}, list(win._value_edits)
    # заголовок времени отражает единицу
    assert "min" in win.lbl_time.text(), win.lbl_time.text()

    # создаём кривую через БД и выбираем в списке
    cid = db.create_curve("aero_malate_1", {"substrate": "malate"},
                          start_iso="2026-07-03 10:00:00")
    win._reload_curves()
    win._select_curve_id(cid)
    assert win._current_curve_id() == cid

    # добавляем точку через методы окна
    win.ed_time.setText("0")
    win._value_edits["OD600"].setText("0.02")
    win._value_edits["pH"].setText("7.0")
    win._add_point()
    win.ed_time.setText("30")
    win._value_edits["OD600"].setText("0.5")
    win._add_point()  # pH пропущен
    assert len(db.list_points(cid)) == 2
    print("[ok] точки добавлены через окно (2 шт)")

    # «Сейчас» подставляет число
    win._fill_now()
    assert win.ed_time.text() and float(win.ed_time.text()) > 0
    print(f"[ok] кнопка 'Сейчас' -> t={win.ed_time.text()} мин")

    # таблица точек: колонки = время + величины, строки = точки
    assert win.points_table.columnCount() == 3
    assert win.points_table.horizontalHeaderItem(0).text() == "time_min"
    assert win.points_table.rowCount() == 2
    print("[ok] таблица точек заполнена (time_min, OD600, pH)")

    # завершение кривой блокирует ввод
    win._finish_curve()
    assert win.entry_box.isEnabled() is False
    print("[ok] завершение кривой блокирует ввод")

    # экспорт через БД (логика окна использует те же вызовы)
    path = db.export_curve(cid, OUT)
    s = load_sample(path)
    assert s.time_column == "time_min"
    assert s.value_columns == ["OD600", "pH"]
    assert s.meta["substrate"] == "malate"
    print("[ok] экспорт прочитан визуализатором (time_min)")

    db.close()
    print("\nВсе GUI-проверки записи пройдены. Файлы в", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
