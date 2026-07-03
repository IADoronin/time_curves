"""Диалог настройки схемы эксперимента: свойства-условия, измеряемые величины,
единица времени."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .db import MeasuredVar, Property, RecordingDB

# Отображение единицы времени -> код.
TIME_UNIT_LABELS = [("Часы", "h"), ("Минуты", "min"), ("Сутки", "d")]


class SchemaDialog(QDialog):
    """Редактор схемы: пишет изменения в БД при подтверждении."""

    def __init__(self, db: RecordingDB, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Схема эксперимента")
        self.resize(560, 520)
        self._build()
        self._load()

    def _build(self) -> None:
        root = QVBoxLayout(self)

        # единица времени
        top = QFormLayout()
        self.cmb_unit = QComboBox()
        for label, code in TIME_UNIT_LABELS:
            self.cmb_unit.addItem(label, code)
        top.addRow("Единица времени:", self.cmb_unit)
        root.addLayout(top)

        # свойства-условия
        gp = QGroupBox("Свойства эксперимента (условия — лист meta)")
        gpv = QVBoxLayout(gp)
        self.tbl_props = QTableWidget(0, 4)
        self.tbl_props.setHorizontalHeaderLabels(
            ["Имя", "Тип", "Варианты (через запятую)", "Единица"]
        )
        self.tbl_props.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        gpv.addWidget(self.tbl_props)
        gpv.addLayout(self._row_buttons(self._add_prop_row, self.tbl_props))
        gpv.addWidget(QLabel("«Варианты» нужны только для типа enum; для numeric игнорируются."))
        root.addWidget(gp)

        # измеряемые величины
        gv = QGroupBox("Измеряемые величины (колонки листа data)")
        gvv = QVBoxLayout(gv)
        self.tbl_vars = QTableWidget(0, 2)
        self.tbl_vars.setHorizontalHeaderLabels(["Имя", "Единица"])
        self.tbl_vars.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        gvv.addWidget(self.tbl_vars)
        gvv.addLayout(self._row_buttons(self._add_var_row, self.tbl_vars))
        root.addWidget(gv)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

    def _row_buttons(self, add_fn, table: QTableWidget) -> QHBoxLayout:
        h = QHBoxLayout()
        b_add = QPushButton("＋ Добавить")
        b_add.clicked.connect(add_fn)
        b_del = QPushButton("－ Удалить выбранную")
        b_del.clicked.connect(lambda: self._del_row(table))
        h.addWidget(b_add)
        h.addWidget(b_del)
        h.addStretch(1)
        return h

    # ---------- строки таблиц ----------
    def _add_prop_row(self, name="", kind="enum", options="", unit="") -> None:
        r = self.tbl_props.rowCount()
        self.tbl_props.insertRow(r)
        self.tbl_props.setItem(r, 0, QTableWidgetItem(name))
        cmb = QComboBox()
        cmb.addItems(["enum", "numeric"])
        cmb.setCurrentText(kind)
        self.tbl_props.setCellWidget(r, 1, cmb)
        self.tbl_props.setItem(r, 2, QTableWidgetItem(options))
        self.tbl_props.setItem(r, 3, QTableWidgetItem(unit))

    def _add_var_row(self, name="", unit="") -> None:
        r = self.tbl_vars.rowCount()
        self.tbl_vars.insertRow(r)
        self.tbl_vars.setItem(r, 0, QTableWidgetItem(name))
        self.tbl_vars.setItem(r, 1, QTableWidgetItem(unit))

    def _del_row(self, table: QTableWidget) -> None:
        r = table.currentRow()
        if r >= 0:
            table.removeRow(r)

    # ---------- загрузка/чтение ----------
    def _load(self) -> None:
        idx = self.cmb_unit.findData(self.db.time_unit)
        self.cmb_unit.setCurrentIndex(max(idx, 0))
        for p in self.db.list_properties():
            self._add_prop_row(
                p.name, p.kind, ", ".join(p.options or []), p.unit or ""
            )
        for v in self.db.list_measured_vars():
            self._add_var_row(v.name, v.unit or "")

    def _cell(self, table: QTableWidget, r: int, c: int) -> str:
        it = table.item(r, c)
        return it.text().strip() if it else ""

    def _read_props(self) -> list[Property]:
        props: list[Property] = []
        for r in range(self.tbl_props.rowCount()):
            name = self._cell(self.tbl_props, r, 0)
            if not name:
                continue
            kind = self.tbl_props.cellWidget(r, 1).currentText()
            opts_raw = self._cell(self.tbl_props, r, 2)
            options = [o.strip() for o in opts_raw.replace(";", ",").split(",") if o.strip()]
            unit = self._cell(self.tbl_props, r, 3) or None
            props.append(Property(name, kind, options if kind == "enum" else None, unit, r))
        return props

    def _read_vars(self) -> list[MeasuredVar]:
        vars_: list[MeasuredVar] = []
        for r in range(self.tbl_vars.rowCount()):
            name = self._cell(self.tbl_vars, r, 0)
            if not name:
                continue
            unit = self._cell(self.tbl_vars, r, 1) or None
            vars_.append(MeasuredVar(name, unit, r))
        return vars_

    def _on_accept(self) -> None:
        props = self._read_props()
        vars_ = self._read_vars()

        # валидация
        pnames = [p.name for p in props]
        if len(pnames) != len(set(pnames)):
            return self._err("Имена свойств должны быть уникальны.")
        for p in props:
            if p.kind == "enum" and not p.options:
                return self._err(f"Для enum-свойства «{p.name}» задайте хотя бы один вариант.")
        vnames = [v.name for v in vars_]
        if len(vnames) != len(set(vnames)):
            return self._err("Имена измеряемых величин должны быть уникальны.")
        if set(pnames) & set(vnames):
            return self._err("Свойство и измеряемая величина не должны иметь одинаковое имя.")

        self.db.time_unit = self.cmb_unit.currentData()
        self.db.replace_properties(props)
        self.db.replace_measured_vars(vars_)
        self.accept()

    def _err(self, msg: str) -> None:
        QMessageBox.warning(self, "Проверка схемы", msg)
