"""Headless smoke-тест: полный конвейр без реального дисплея.

Запуск:
    QT_QPA_PLATFORM=offscreen python tests/smoke_test.py
Сохраняет отрендеренные графики в tmp/ для визуальной проверки.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QTreeWidgetItem

from growth_viz.main_window import MainWindow

OUT = ROOT / "tmp"
OUT.mkdir(exist_ok=True)


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.load_folder(ROOT / "test_data")

    # 1) контролы наполнились
    groups = [win.group_combo.itemText(i) for i in range(win.group_combo.count())]
    values = [win.value_combo.itemText(i) for i in range(win.value_combo.count())]
    assert groups == ["aeration", "co2", "substrate"], groups
    assert values == ["OD600", "pH", "substrate_mM"], values
    print("[ok] контролы:", groups, "|", values)

    # 2) дерево образцов построено под текущую группировку
    top_count = win.tree.topLevelItemCount()
    child_total = sum(win.tree.topLevelItem(i).childCount() for i in range(top_count))
    assert child_total == 6, child_total
    print(f"[ok] дерево: {top_count} групп, {child_total} образцов")

    # группируем по substrate для наглядного графика
    win.group_combo.setCurrentText("substrate")
    win.value_combo.setCurrentText("OD600")
    win.canvas.fig.savefig(OUT / "01_substrate_OD600_all.png", dpi=110)
    print("[ok] график: substrate / OD600 (все повторы)")

    # 3) выключаем один образец и проверяем, что перерисовка учитывает это
    # находим первый дочерний элемент и снимаем галку
    for i in range(win.tree.topLevelItemCount()):
        top = win.tree.topLevelItem(i)
        if top.childCount():
            child: QTreeWidgetItem = top.child(0)
            sample = child.data(0, Qt.ItemDataRole.UserRole)
            child.setCheckState(0, Qt.CheckState.Unchecked)
            assert sample.enabled is False, "снятие галки не отключило образец"
            print(f"[ok] выключен образец: {sample.name}")
            break
    win.canvas.fig.savefig(OUT / "02_substrate_OD600_one_off.png", dpi=110)

    # 4) переключение показателя и группировки
    win.value_combo.setCurrentText("pH")
    win.group_combo.setCurrentText("co2")
    win.canvas.fig.savefig(OUT / "03_co2_pH.png", dpi=110)
    print("[ok] переключение показателя/группировки")

    # 5) панель настроек: точки, крупный шрифт, шаг осей, заголовок
    sp = win.settings_panel
    win.group_combo.setCurrentText("substrate")
    win.value_combo.setCurrentText("OD600")
    sp.cb_markers.setChecked(True)
    sp.sp_marker_size.setValue(6.0)
    sp.sp_font.setValue(14)
    sp.cmb_font.setCurrentText("DejaVu Serif")
    sp.sp_xstep.setValue(6.0)
    sp.sp_ystep.setValue(0.2)
    sp.ed_title.setText("Рост на разных субстратах")
    settings = sp.to_settings()
    assert settings.show_markers and settings.font_size == 14
    assert settings.x_tick_step == 6.0 and settings.title
    win.canvas.fig.savefig(OUT / "04_settings_applied.png", dpi=110)
    print("[ok] панель настроек применена:", settings)

    # 6) конвертация единиц: физический размер не меняется
    sp.cmb_unit.setCurrentText("см")
    sp.sp_width.setValue(12.0)
    sp.sp_height.setValue(8.0)
    assert abs(sp.width_in() - 12.0 / 2.54) < 1e-6
    sp.cmb_unit.setCurrentText("дюйм")
    # спинбокс округляет до 2 знаков -> допуск 0.01
    assert abs(sp.sp_width.value() - 12.0 / 2.54) < 0.01, sp.sp_width.value()
    print("[ok] конвертация единиц см<->дюйм сохраняет размер")

    # 7) экспорт: файл нужного размера в пикселях
    import matplotlib.image as mpimg
    sp.cmb_unit.setCurrentText("дюйм")
    sp.sp_width.setValue(6.0)
    sp.sp_height.setValue(4.0)
    sp.sp_dpi.setValue(200)
    out_png = OUT / "05_export_1200x800.png"
    win.canvas.export(str(out_png), sp.to_settings())
    arr = mpimg.imread(str(out_png))
    assert arr.shape[1] == 1200 and arr.shape[0] == 800, arr.shape
    print(f"[ok] экспорт PNG {arr.shape[1]}x{arr.shape[0]} px @200dpi")

    # 8) экспорт в PDF (векторный формат для статей)
    out_pdf = OUT / "06_export.pdf"
    win.canvas.export(str(out_pdf), sp.to_settings())
    assert out_pdf.exists() and out_pdf.stat().st_size > 0
    print("[ok] экспорт PDF (вектор)")

    # 9) предпросмотр в пропорциях экспорта
    sp.cb_lock_aspect.setChecked(True)
    win._replot()
    assert win.aspect.ratio is not None
    assert abs(win.aspect.ratio - 6.0 / 4.0) < 1e-6, win.aspect.ratio
    print(f"[ok] предпросмотр заблокирован на {win.aspect.ratio:.2f}:1")

    # 10) выравнивание: внутри группы ориентиры сходятся, между группами — нет
    import numpy as np
    from growth_viz import apply_alignment, load_folder
    from growth_viz.alignment import _crossing_time

    def crossing(s, use_shift, lvl=0.2):
        t = s.times() if use_shift else s.raw_times()
        y = s.data["OD600"].to_numpy(float)
        o = np.argsort(t)
        return _crossing_time(t[o], y[o], lvl)

    S2 = load_folder(ROOT / "test_data")
    malate = [s for s in S2 if s.meta["substrate"] == "malate"]
    acetate = [s for s in S2 if s.meta["substrate"] == "acetate"]
    raw_mal = [crossing(s, False) for s in malate]
    raw_ace = [crossing(s, False) for s in acetate]
    apply_alignment(S2, ref_col="OD600", method="threshold", level=0.2, group_key="substrate")
    ali_mal = [crossing(s, True) for s in malate]
    ali_ace = [crossing(s, True) for s in acetate]
    # внутри каждой группы разброс ориентиров был, а после выравнивания свёлся к 0
    assert np.nanmax(raw_mal) - np.nanmin(raw_mal) > 1.0, raw_mal
    assert np.nanmax(ali_mal) - np.nanmin(ali_mal) < 1e-6, ali_mal
    assert np.nanmax(ali_ace) - np.nanmin(ali_ace) < 1e-6, ali_ace
    # группы выравниваются независимо: якорь = среднее ориентиров своей группы
    assert abs(np.nanmean(ali_mal) - np.nanmean(raw_mal)) < 1e-6
    assert abs(np.nanmean(ali_ace) - np.nanmean(raw_ace)) < 1e-6
    print(f"[ok] выравнивание: malate {[round(x,1) for x in raw_mal]} "
          f"→ все в {np.nanmean(ali_mal):.1f} ч; группы выравниваются независимо")

    # 11) рендер «до/после» на общем окне
    win.load_folder(ROOT / "test_data")
    win.group_combo.setCurrentText("substrate")
    win.value_combo.setCurrentText("OD600")
    win.settings_panel.cb_markers.setChecked(True)
    win.cb_align.setChecked(False)
    win._replot()
    win.canvas.fig.savefig(OUT / "07_before_align.png", dpi=120)
    win.cb_align.setChecked(True)
    win._replot()
    win.canvas.fig.savefig(OUT / "08_after_align.png", dpi=120)
    print("[ok] рендер до/после выравнивания")

    print("\nВсе проверки пройдены. Файлы сохранены в", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
