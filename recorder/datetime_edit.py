"""Виджет ввода даты+времени с клавиатуры (+ кнопка-календарь).

В отличие от QDateTimeEdit, тут обычное текстовое поле — можно свободно печатать
дату, а не «крутить от 1900». Кнопка «📅» открывает календарь для мыши.
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import QDate, pyqtSignal
from PyQt6.QtWidgets import (
    QCalendarWidget,
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

# Форматы, которые принимаем при вводе (первый — канонический для вывода).
_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
)
DISPLAY_FORMAT = "%Y-%m-%d %H:%M:%S"


def parse_datetime(text: str) -> datetime:
    """Разобрать дату+время из свободного текста. ValueError, если не вышло."""
    s = text.strip()
    for fmt in _FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"не удалось разобрать дату: {text!r}")


class DateTimeEdit(QWidget):
    """Текстовое поле даты+времени + кнопка-календарь. Ввод с клавиатуры."""

    returnPressed = pyqtSignal()  # проброс Enter из текстового поля

    def __init__(self, parent=None):
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText("ГГГГ-ММ-ДД ЧЧ:ММ:СС")
        self.edit.returnPressed.connect(self.returnPressed)
        h.addWidget(self.edit, stretch=1)

        self.btn_cal = QPushButton("📅")
        self.btn_cal.setFixedWidth(34)
        self.btn_cal.setFocusPolicy(self.btn_cal.focusPolicy().NoFocus)
        self.btn_cal.clicked.connect(self._pick_calendar)
        h.addWidget(self.btn_cal)

    # ---------- значение ----------
    def setValue(self, dt: datetime) -> None:
        self.edit.setText(dt.strftime(DISPLAY_FORMAT))

    def text(self) -> str:
        return self.edit.text()

    def value(self) -> datetime:
        """Текущее значение как datetime (ValueError при неверном вводе)."""
        return parse_datetime(self.edit.text())

    def setFocusToText(self) -> None:
        self.edit.setFocus()
        self.edit.selectAll()

    # ---------- календарь ----------
    def _pick_calendar(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Выбор даты")
        v = QVBoxLayout(dlg)
        cal = QCalendarWidget()
        # стартуем с текущего значения, если оно валидно
        try:
            d = self.value().date()
            cal.setSelectedDate(QDate(d.year, d.month, d.day))
        except ValueError:
            pass
        v.addWidget(cal)
        cal.activated.connect(dlg.accept)  # двойной клик по дню — ок
        if dlg.exec():
            qd = cal.selectedDate()
            # сохраняем набранное время, меняем только дату
            try:
                cur = self.value()
                t = cur.time()
            except ValueError:
                t = datetime.now().time()
            self.setValue(datetime(qd.year(), qd.month(), qd.day(),
                                   t.hour, t.minute, t.second))
        self.edit.setFocus()
