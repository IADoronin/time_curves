"""Главное окно приложения записи кривых."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QAction,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QShortcut,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from growth_viz.main_window import MainWindow as VizWindow

from .datetime_edit import DISPLAY_FORMAT, DateTimeEdit
from .db import FLAG_COUNT, FLAG_LABELS, RecordingDB
from .new_curve_dialog import NewCurveDialog
from .schema_dialog import SchemaDialog
from .uiutil import double_validator, parse_float


class RecordWindow(QMainWindow):
    def __init__(self, db: RecordingDB | None = None):
        super().__init__()
        self.setWindowTitle("Запись кривых")
        self.resize(1000, 640)
        self.db: RecordingDB | None = None
        self._value_edits: dict[str, QLineEdit] = {}
        self._viz_window: VizWindow | None = None  # окно графиков (переиспользуем)
        self._build()
        if db is not None:
            self.set_db(db)

    # ---------- построение ----------
    def _build(self) -> None:
        self._build_menu()

        splitter = QSplitter(Qt.Horizontal)

        # слева: список кривых + кнопки
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(QLabel("Кривые (ПКМ — флаги/удаление):"))
        self.curve_list = QListWidget()
        self.curve_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.curve_list.currentItemChanged.connect(self._on_select_curve)
        self.curve_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.curve_list.customContextMenuRequested.connect(self._curve_menu)
        lv.addWidget(self.curve_list, stretch=1)
        QShortcut(QKeySequence.Delete, self.curve_list,
                  activated=self._delete_curves,
                  context=Qt.WidgetShortcut)

        self.btn_new = QPushButton("Новая кривая")
        self.btn_new.clicked.connect(self._new_curve)
        self.btn_finish = QPushButton("Завершить кривую")
        self.btn_finish.clicked.connect(self._finish_curve)
        self.btn_del_curve = QPushButton("Удалить кривые")
        self.btn_del_curve.clicked.connect(self._delete_curves)
        lv.addWidget(self.btn_new)
        lv.addWidget(self.btn_finish)
        lv.addWidget(self.btn_del_curve)
        splitter.addWidget(left)

        # справа: сводка + ввод точки + таблица точек
        right = QWidget()
        rv = QVBoxLayout(right)
        self.lbl_meta = QLabel("Кривая не выбрана")
        self.lbl_meta.setWordWrap(True)
        rv.addWidget(self.lbl_meta)

        self.entry_box = QGroupBox("Добавить точку")
        ev = QVBoxLayout(self.entry_box)
        time_row = QHBoxLayout()
        self.dt_time = DateTimeEdit()
        self.dt_time.returnPressed.connect(self._add_point)
        self.btn_now = QPushButton("Сейчас")
        self.btn_now.setFocusPolicy(Qt.NoFocus)  # Tab его пропускает
        self.btn_now.clicked.connect(self._fill_now)
        self.lbl_time = QLabel("Дата/время:")
        time_row.addWidget(self.lbl_time)
        time_row.addWidget(self.dt_time, stretch=1)
        time_row.addWidget(self.btn_now)
        ev.addLayout(time_row)

        # живые часы + человекочитаемая подсказка «сейчас»
        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("color: gray;")
        ev.addWidget(self.lbl_clock)
        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(1000)
        self._tick_clock()

        self.values_form = QFormLayout()   # поля измеряемых величин (по схеме)
        ev.addLayout(self.values_form)

        self.btn_add = QPushButton("Добавить точку")
        self.btn_add.clicked.connect(self._add_point)
        ev.addWidget(self.btn_add)
        rv.addWidget(self.entry_box)

        self.points_table = QTableWidget(0, 0)
        self.points_table.setSelectionBehavior(
            QAbstractItemView.SelectRows)
        self.points_table.setSelectionMode(
            QAbstractItemView.ExtendedSelection)
        rv.addWidget(self.points_table, stretch=1)
        QShortcut(QKeySequence.Delete, self.points_table,
                  activated=self._delete_points,
                  context=Qt.WidgetShortcut)

        tb = QHBoxLayout()
        self.btn_del_point = QPushButton("Удалить точки")
        self.btn_del_point.clicked.connect(self._delete_points)
        self.btn_plots = QPushButton("Графики")
        self.btn_plots.clicked.connect(self._open_plots)
        self.btn_export = QPushButton("Экспорт в Excel…")
        self.btn_export.clicked.connect(self._export_current)
        self.btn_export_sel = QPushButton("Экспорт выбранных…")
        self.btn_export_sel.clicked.connect(self._export_selected)
        tb.addWidget(self.btn_del_point)
        tb.addStretch(1)
        tb.addWidget(self.btn_plots)
        tb.addWidget(self.btn_export_sel)
        tb.addWidget(self.btn_export)
        rv.addLayout(tb)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([280, 720])
        self.setCentralWidget(splitter)
        self.statusBar()

    def _build_menu(self) -> None:
        m_file = self.menuBar().addMenu("Файл")
        for title, slot in [
            ("Новый эксперимент / открыть базу…", self._open_db_dialog),
            ("Экспорт всех…", self._export_all),
        ]:
            act = QAction(title, self)
            act.triggered.connect(slot)
            m_file.addAction(act)

        m_exp = self.menuBar().addMenu("Эксперимент")
        act = QAction("Поля эксперимента (схема)…", self)
        act.triggered.connect(self._edit_schema)
        m_exp.addAction(act)

        m_view = self.menuBar().addMenu("Вид")
        act = QAction("Открыть графики", self)
        act.triggered.connect(self._open_plots)
        m_view.addAction(act)

    # ---------- БД ----------
    def set_db(self, db: RecordingDB) -> None:
        self.db = db
        self.setWindowTitle(f"Запись кривых — {db.path.name}")
        self._rebuild_value_fields()
        self._reload_curves()
        self._update_time_label()
        # Новый (пустой) эксперимент — сразу предложить задать поля и ограничения.
        QTimer.singleShot(0, self._maybe_prompt_schema)

    def _maybe_prompt_schema(self) -> None:
        if self.db and self.db.is_empty_schema():
            QMessageBox.information(
                self, "Новый эксперимент",
                "Сначала задайте поля эксперимента и ограничения на них "
                "(типы, варианты для списков, границы для чисел).",
            )
            self._edit_schema()

    def _open_db_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Новая или существующая база", "experiment.db", "SQLite (*.db)",
            options=QFileDialog.DontConfirmOverwrite,
        )
        if path:
            if self.db is not None:
                self.db.close()
            self.set_db(RecordingDB(path))

    def _edit_schema(self) -> None:
        if not self._require_db():
            return
        if SchemaDialog(self.db, self).exec():
            self._rebuild_value_fields()
            self._update_time_label()
            self._reload_points()  # заголовки таблицы могли измениться
            self.statusBar().showMessage("Схема обновлена", 3000)

    # ---------- список кривых ----------
    def _reload_curves(self) -> None:
        self.curve_list.blockSignals(True)
        self.curve_list.clear()
        for c in self.db.list_curves():
            mark = "✓ " if c.finished else "● "
            it = QListWidgetItem(f"{c.flag_prefix()}{mark}{c.name}")
            it.setData(Qt.UserRole, c.id)
            self.curve_list.addItem(it)
        self.curve_list.blockSignals(False)
        self._on_select_curve(self.curve_list.currentItem(), None)

    def _selected_curve_ids(self) -> list[int]:
        ids = [it.data(Qt.UserRole) for it in self.curve_list.selectedItems()]
        return ids

    def _current_curve_id(self) -> int | None:
        it = self.curve_list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _on_select_curve(self, cur, _prev) -> None:
        cid = cur.data(Qt.UserRole) if cur else None
        if cid is None:
            self.lbl_meta.setText("Кривая не выбрана")
            self.entry_box.setEnabled(False)
            self._reload_points()
            return
        curve = self.db.get_curve(cid)
        meta = self.db.get_curve_meta(cid)
        meta_str = ", ".join(f"{k}={v}" for k, v in meta.items()) or "(без условий)"
        state = "завершена" if curve.finished else "в работе"
        self.lbl_meta.setText(
            f"<b>{curve.name}</b> — {state}<br>старт: {curve.start_iso}<br>{meta_str}"
        )
        self.entry_box.setEnabled(not curve.finished)
        self._reload_points()

    # ---------- поля значений ----------
    def _rebuild_value_fields(self) -> None:
        while self.values_form.rowCount():
            self.values_form.removeRow(0)
        self._value_edits.clear()
        if not self.db:
            return
        for v in self.db.list_measured_vars():
            ed = QLineEdit()
            ed.setValidator(double_validator())
            ed.setPlaceholderText("число" + (f", {v.unit}" if v.unit else ""))
            ed.returnPressed.connect(self._add_point)   # Enter добавляет точку
            label = v.name + (f", {v.unit}" if v.unit else "")
            self.values_form.addRow(label + ":", ed)
            self._value_edits[v.name] = ed
        # Таб-порядок: поле даты → поля значений → кнопка «Добавить точку».
        prev = self.dt_time.edit
        for ed in self._value_edits.values():
            self.setTabOrder(prev, ed)
            prev = ed
        self.setTabOrder(prev, self.btn_add)

    def _update_time_label(self) -> None:
        self.lbl_time.setText("Дата/время:")

    # ---------- точки ----------
    @staticmethod
    def _fmt_time(t: float) -> str:
        """Человекочитаемое число времени (до 2 знаков, без лишних нулей)."""
        s = f"{t:.2f}".rstrip("0").rstrip(".")
        return s or "0"

    def _tick_clock(self) -> None:
        now = datetime.now().strftime("%H:%M:%S")
        txt = f"текущее время: {now}"
        cid = self._current_curve_id()
        if cid is not None and self.db:
            el = self.db.elapsed_since_start(cid)
            txt += f"   ·   от старта: {self._fmt_time(el)} ч"
        self.lbl_clock.setText(txt)

    def _fill_now(self) -> None:
        self.dt_time.setValue(datetime.now().replace(microsecond=0))
        # сразу перевести фокус на первое поле значения (удобно печатать далее)
        for ed in self._value_edits.values():
            ed.setFocus()
            break

    def _add_point(self) -> None:
        cid = self._current_curve_id()
        if cid is None:
            return
        if not self.dt_time.text().strip():
            QMessageBox.warning(self, "Точка", "Укажите дату/время (или нажмите «Сейчас»).")
            return
        try:
            ts = self.dt_time.value()
        except ValueError:
            QMessageBox.warning(self, "Точка",
                               "Неверная дата/время. Формат «ГГГГ-ММ-ДД ЧЧ:ММ».")
            return
        # проверка хронологии (не блокирует, только предупреждает)
        last = self.db.last_ts(cid)
        if last is not None and ts <= last:
            resp = QMessageBox.question(
                self, "Точка",
                f"Время не позже предыдущего ({last:%Y-%m-%d %H:%M}). Всё равно добавить?",
            )
            if resp != QMessageBox.Yes:
                return
        values: dict[str, float] = {}
        for name, ed in self._value_edits.items():
            s = ed.text().strip()
            if not s:
                continue
            try:
                values[name] = parse_float(s)
            except ValueError:
                QMessageBox.warning(self, "Точка", f"Значение «{name}» должно быть числом.")
                return
        self.db.add_point(cid, ts, values,
                         recorded_iso=datetime.now().isoformat(sep=" ", timespec="seconds"))
        for ed in self._value_edits.values():
            ed.clear()
        self.dt_time.setValue(datetime.now().replace(microsecond=0))
        self.dt_time.setFocusToText()               # фокус обратно в поле даты
        self._reload_points()
        self.statusBar().showMessage(f"Точка {ts:%Y-%m-%d %H:%M} добавлена", 2000)

    def _reload_points(self) -> None:
        cid = self._current_curve_id()
        cols = ["дата/время", *self.db.measured_names()] if self.db else []
        self.points_table.clear()
        self.points_table.setColumnCount(len(cols))
        self.points_table.setHorizontalHeaderLabels(cols)
        if cid is None or not self.db:
            self.points_table.setRowCount(0)
            return
        points = self.db.list_points(cid)
        self.points_table.setRowCount(len(points))
        vars_ = self.db.measured_names()
        for r, p in enumerate(points):
            ts_txt = p.ts.strftime(DISPLAY_FORMAT) if p.ts else ""
            t_item = QTableWidgetItem(ts_txt)
            t_item.setData(Qt.UserRole, p.id)
            self.points_table.setItem(r, 0, t_item)
            for c, var in enumerate(vars_, start=1):
                val = p.values.get(var)
                self.points_table.setItem(
                    r, c, QTableWidgetItem("" if val is None else f"{val:g}")
                )

    def _delete_points(self) -> None:
        rows = {ix.row() for ix in self.points_table.selectedIndexes()}
        if not rows and self.points_table.currentRow() >= 0:
            rows = {self.points_table.currentRow()}
        pids = []
        for r in rows:
            it = self.points_table.item(r, 0)
            if it and it.data(Qt.UserRole) is not None:
                pids.append(it.data(Qt.UserRole))
        for pid in pids:
            self.db.delete_point(pid)
        if pids:
            self._reload_points()

    # ---------- кривые: создание/завершение ----------
    def _new_curve(self) -> None:
        if not self._require_db():
            return
        dlg = NewCurveDialog(self.db, self)
        if dlg.exec():
            name, meta, start_iso = dlg.result_data()
            cid = self.db.create_curve(name, meta, start_iso)
            self._reload_curves()
            self._select_curve_id(cid)

    def _finish_curve(self) -> None:
        cid = self._current_curve_id()
        if cid is None:
            return
        self.db.set_finished(cid, True)
        self._reload_curves()
        self._select_curve_id(cid)

    def _select_curve_id(self, cid: int) -> None:
        for i in range(self.curve_list.count()):
            if self.curve_list.item(i).data(Qt.UserRole) == cid:
                self.curve_list.setCurrentRow(i)
                return

    def _delete_curves(self) -> None:
        ids = self._selected_curve_ids()
        if not ids:
            return
        names = [self.db.get_curve(i).name for i in ids]
        preview = ", ".join(names[:5]) + ("…" if len(names) > 5 else "")
        resp = QMessageBox.question(
            self, "Удаление кривых",
            f"Удалить кривые ({len(ids)}): {preview}?\nТочки этих кривых тоже удалятся.",
        )
        if resp != QMessageBox.Yes:
            return
        for i in ids:
            self.db.delete_curve(i)
        self._reload_curves()

    def _curve_menu(self, pos) -> None:
        item = self.curve_list.itemAt(pos)
        if item is None:
            return
        cid = item.data(Qt.UserRole)
        flags = self.db.get_flags(cid)
        menu = QMenu(self)
        for i in range(FLAG_COUNT):
            act = menu.addAction(f"{FLAG_LABELS[i]} Флаг {i + 1}")
            act.setCheckable(True)
            act.setChecked(bool(flags & (1 << i)))
            act.triggered.connect(lambda _checked, c=cid, idx=i: self._toggle_flag(c, idx))
        menu.addSeparator()
        menu.addAction("Удалить кривые", self._delete_curves)
        menu.exec(self.curve_list.mapToGlobal(pos))

    def _toggle_flag(self, cid: int, index: int) -> None:
        self.db.toggle_flag(cid, index)
        self._reload_curves()
        self._select_curve_id(cid)

    # ---------- экспорт ----------
    def _export_current(self) -> None:
        cid = self._current_curve_id()
        if cid is None:
            return
        curve = self.db.get_curve(cid)
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт кривой", f"{curve.name}.xlsx", "Excel (*.xlsx)"
        )
        if not path:
            return
        p = Path(path)
        self.db.export_curve(cid, p.parent, filename=p.name)
        self.statusBar().showMessage(f"Сохранено: {path}", 5000)

    def _export_all(self) -> None:
        if not self._require_db():
            return
        folder = QFileDialog.getExistingDirectory(self, "Папка для экспорта всех кривых")
        if not folder:
            return
        paths = self.db.export_all(folder)
        self.statusBar().showMessage(f"Экспортировано файлов: {len(paths)}", 5000)

    def _export_selected(self) -> None:
        """Батч-экспорт: выбранные кривые (или все, если выбор пуст) в папку."""
        if not self._require_db():
            return
        ids = self._selected_curve_ids()
        if not ids:
            ids = [c.id for c in self.db.list_curves()]
        if not ids:
            QMessageBox.information(self, "Экспорт", "Нет кривых для экспорта.")
            return
        folder = QFileDialog.getExistingDirectory(
            self, f"Папка для экспорта ({len(ids)} кривых)")
        if not folder:
            return
        paths = self.db.export_curves(ids, folder)
        self.statusBar().showMessage(f"Экспортировано файлов: {len(paths)}", 5000)

    def _open_plots(self) -> None:
        """Открыть окно визуализатора по текущим кривым (экспорт во вспом. папку)."""
        if not self._require_db():
            return
        folder = self.db.path.parent / f"{self.db.path.stem}_plots"
        folder.mkdir(exist_ok=True)
        for f in folder.glob("*.xlsx"):     # убрать устаревшие/удалённые кривые
            f.unlink()
        paths = self.db.export_all(folder, skip_empty=True)
        if not paths:
            QMessageBox.information(self, "Графики", "Пока нет ни одной точки для построения.")
            return
        if self._viz_window is None:
            self._viz_window = VizWindow()
        self._viz_window.load_folder(folder)
        self._viz_window.show()
        self._viz_window.raise_()
        self._viz_window.activateWindow()
        self.statusBar().showMessage(f"Графики обновлены: кривых {len(paths)}", 4000)

    # ---------- утилиты ----------
    def _require_db(self) -> bool:
        if self.db is None:
            QMessageBox.information(self, "База", "Сначала создайте или откройте базу (меню «Файл»).")
            return False
        return True
