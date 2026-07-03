"""Диалог создания новой кривой: поля по схеме эксперимента + имя + старт."""

from __future__ import annotations

import re
from datetime import datetime

from PyQt6.QtCore import QDateTime
from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
)

from .db import RecordingDB


def _suggest_name(meta: dict[str, object]) -> str:
    """Автоимя кривой из значений условий: соединить через '_'."""
    parts = [str(v).strip() for v in meta.values() if str(v).strip()]
    name = "_".join(parts)
    return re.sub(r"[^\w.-]+", "_", name, flags=re.UNICODE).strip("_")


class NewCurveDialog(QDialog):
    """Собирает meta по схеме, имя и время старта."""

    def __init__(self, db: RecordingDB, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Новая кривая")
        self.resize(380, 320)
        self._editors: dict[str, object] = {}
        self._name_touched = False
        self._build()

    def _build(self) -> None:
        form = QFormLayout(self)

        # поля условий по схеме
        for p in self.db.list_properties():
            if p.kind == "enum":
                w = QComboBox()
                w.addItems(p.options or [])
                w.currentIndexChanged.connect(self._refresh_name)
            else:
                w = QLineEdit()
                validator = QDoubleValidator()
                if p.min_val is not None:
                    validator.setBottom(p.min_val)
                if p.max_val is not None:
                    validator.setTop(p.max_val)
                w.setValidator(validator)
                ph = "число"
                if p.min_val is not None or p.max_val is not None:
                    lo = "" if p.min_val is None else f"{p.min_val:g}"
                    hi = "" if p.max_val is None else f"{p.max_val:g}"
                    ph += f" {lo}..{hi}"
                if p.unit:
                    ph += f", {p.unit}"
                w.setPlaceholderText(ph)
                w.textChanged.connect(self._refresh_name)
            label = p.name + (f", {p.unit}" if p.unit and p.kind != "enum" else "")
            form.addRow(label + ":", w)
            self._editors[p.name] = w

        # имя кривой (автоподсказка, но можно править вручную)
        self.ed_name = QLineEdit()
        self.ed_name.textEdited.connect(self._on_name_edited)
        form.addRow("Имя кривой:", self.ed_name)

        # время старта
        self.dt_start = QDateTimeEdit(QDateTime.currentDateTime())
        self.dt_start.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.dt_start.setCalendarPopup(True)
        form.addRow("Старт:", self.dt_start)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        bb.accepted.connect(self._on_accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

        self._refresh_name()

    # ---------- имя ----------
    def _on_name_edited(self, _text: str) -> None:
        self._name_touched = True

    def _refresh_name(self, *_a) -> None:
        if self._name_touched:
            return
        self.ed_name.setText(_suggest_name(self._collect_meta()))

    def _collect_meta(self) -> dict[str, object]:
        meta: dict[str, object] = {}
        for name, w in self._editors.items():
            if isinstance(w, QComboBox):
                meta[name] = w.currentText()
            else:
                meta[name] = w.text().strip()
        return meta

    # ---------- результат ----------
    def _on_accept(self) -> None:
        name = self.ed_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Новая кривая", "Укажите имя кривой.")
            return
        # проверка числовых полей и границ
        for p in self.db.list_properties():
            if p.kind != "numeric":
                continue
            txt = self._editors[p.name].text().strip()
            if not txt:
                continue
            try:
                val = float(txt)
            except ValueError:
                QMessageBox.warning(self, "Новая кривая",
                                   f"Поле «{p.name}» должно быть числом.")
                return
            if p.min_val is not None and val < p.min_val:
                QMessageBox.warning(self, "Новая кривая",
                                   f"«{p.name}»: не меньше {p.min_val:g}.")
                return
            if p.max_val is not None and val > p.max_val:
                QMessageBox.warning(self, "Новая кривая",
                                   f"«{p.name}»: не больше {p.max_val:g}.")
                return
        self.accept()

    def result_data(self) -> tuple[str, dict[str, object], str]:
        """(имя, meta, start_iso) — вызывать после exec()==Accepted."""
        start = self.dt_start.dateTime().toPyDateTime().replace(microsecond=0)
        return self.ed_name.text().strip(), self._collect_meta(), start.isoformat(sep=" ")
