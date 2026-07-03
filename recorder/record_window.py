"""Главное окно приложения записи кривых."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QDoubleValidator
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .db import RecordingDB
from .new_curve_dialog import NewCurveDialog
from .schema_dialog import SchemaDialog


class RecordWindow(QMainWindow):
    def __init__(self, db: RecordingDB | None = None):
        super().__init__()
        self.setWindowTitle("Запись кривых")
        self.resize(1000, 640)
        self.db: RecordingDB | None = None
        self._value_edits: dict[str, QLineEdit] = {}
        self._build()
        if db is not None:
            self.set_db(db)

    # ---------- построение ----------
    def _build(self) -> None:
        self._build_menu()

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # слева: список кривых + кнопки
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(QLabel("Кривые:"))
        self.curve_list = QListWidget()
        self.curve_list.currentItemChanged.connect(self._on_select_curve)
        lv.addWidget(self.curve_list, stretch=1)
        self.btn_new = QPushButton("Новая кривая")
        self.btn_new.clicked.connect(self._new_curve)
        self.btn_finish = QPushButton("Завершить кривую")
        self.btn_finish.clicked.connect(self._finish_curve)
        lv.addWidget(self.btn_new)
        lv.addWidget(self.btn_finish)
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
        self.ed_time = QLineEdit()
        self.ed_time.setValidator(QDoubleValidator())
        self.ed_time.setPlaceholderText("время от старта")
        self.btn_now = QPushButton("Сейчас")
        self.btn_now.clicked.connect(self._fill_now)
        self.lbl_time = QLabel("Время:")
        time_row.addWidget(self.lbl_time)
        time_row.addWidget(self.ed_time, stretch=1)
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
        rv.addWidget(self.points_table, stretch=1)
        tb = QHBoxLayout()
        self.btn_del_point = QPushButton("Удалить точку")
        self.btn_del_point.clicked.connect(self._delete_point)
        self.btn_export = QPushButton("Экспорт в Excel…")
        self.btn_export.clicked.connect(self._export_current)
        tb.addWidget(self.btn_del_point)
        tb.addStretch(1)
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
            options=QFileDialog.Option.DontConfirmOverwrite,
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
            it = QListWidgetItem(mark + c.name)
            it.setData(Qt.ItemDataRole.UserRole, c.id)
            self.curve_list.addItem(it)
        self.curve_list.blockSignals(False)
        self._on_select_curve(self.curve_list.currentItem(), None)

    def _current_curve_id(self) -> int | None:
        it = self.curve_list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _on_select_curve(self, cur, _prev) -> None:
        cid = cur.data(Qt.ItemDataRole.UserRole) if cur else None
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
            ed.setValidator(QDoubleValidator())
            ed.setPlaceholderText("число" + (f", {v.unit}" if v.unit else ""))
            label = v.name + (f", {v.unit}" if v.unit else "")
            self.values_form.addRow(label + ":", ed)
            self._value_edits[v.name] = ed

    def _update_time_label(self) -> None:
        if self.db:
            self.lbl_time.setText(f"Время ({self.db.time_unit}):")

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
            txt += f"   ·   от старта: {self._fmt_time(el)} {self.db.time_unit}"
        self.lbl_clock.setText(txt)

    def _fill_now(self) -> None:
        cid = self._current_curve_id()
        if cid is None:
            return
        self.ed_time.setText(self._fmt_time(self.db.elapsed_since_start(cid)))

    def _add_point(self) -> None:
        cid = self._current_curve_id()
        if cid is None:
            return
        txt = self.ed_time.text().strip()
        if not txt:
            QMessageBox.warning(self, "Точка", "Укажите время (или нажмите «Сейчас»).")
            return
        try:
            t = float(txt)
        except ValueError:
            QMessageBox.warning(self, "Точка", "Время должно быть числом.")
            return
        # проверка монотонности (не блокирует, только предупреждает)
        last = self.db.last_time(cid)
        if last is not None and t <= last:
            resp = QMessageBox.question(
                self, "Точка",
                f"Время {t} не больше предыдущего ({last}). Всё равно добавить?",
            )
            if resp != QMessageBox.StandardButton.Yes:
                return
        values: dict[str, float] = {}
        for name, ed in self._value_edits.items():
            s = ed.text().strip()
            if not s:
                continue
            try:
                values[name] = float(s)
            except ValueError:
                QMessageBox.warning(self, "Точка", f"Значение «{name}» должно быть числом.")
                return
        self.db.add_point(cid, t, values,
                         recorded_iso=datetime.now().isoformat(sep=" ", timespec="seconds"))
        self.ed_time.clear()
        for ed in self._value_edits.values():
            ed.clear()
        self._reload_points()
        self.statusBar().showMessage(f"Точка t={t} добавлена", 2000)

    def _reload_points(self) -> None:
        cid = self._current_curve_id()
        cols = [self.db.time_column, *self.db.measured_names()] if self.db else []
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
            t_item = QTableWidgetItem(self._fmt_time(p.t))
            t_item.setData(Qt.ItemDataRole.UserRole, p.id)
            self.points_table.setItem(r, 0, t_item)
            for c, var in enumerate(vars_, start=1):
                val = p.values.get(var)
                self.points_table.setItem(
                    r, c, QTableWidgetItem("" if val is None else f"{val:g}")
                )

    def _delete_point(self) -> None:
        r = self.points_table.currentRow()
        if r < 0:
            return
        it = self.points_table.item(r, 0)
        pid = it.data(Qt.ItemDataRole.UserRole) if it else None
        if pid is not None:
            self.db.delete_point(pid)
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
            if self.curve_list.item(i).data(Qt.ItemDataRole.UserRole) == cid:
                self.curve_list.setCurrentRow(i)
                return

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

    # ---------- утилиты ----------
    def _require_db(self) -> bool:
        if self.db is None:
            QMessageBox.information(self, "База", "Сначала создайте или откройте базу (меню «Файл»).")
            return False
        return True
