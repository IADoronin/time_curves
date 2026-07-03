"""Единая точка входа: выбор приложения — визуализатор или запись.

Используется как основной исполняемый файл в упакованных сборках.
Запуск с ``--selftest`` выполняет быстрый round-trip записи/чтения .xlsx и
выходит — так можно проверить работоспособность любой собранной сборки.
"""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class Launcher(QWidget):
    """Маленькое окно выбора приложения."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Кривые роста")
        self._windows: list[QWidget] = []  # держим ссылки, чтобы не собрал GC

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 24)
        v.setSpacing(12)

        title = QLabel("Кривые роста")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)

        sub = QLabel("Выберите приложение")
        sub.setStyleSheet("color: gray;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(sub)
        v.addSpacing(8)

        b_viz = QPushButton("📈   Визуализатор")
        b_viz.clicked.connect(self._open_viz)
        b_rec = QPushButton("✎   Запись данных")
        b_rec.clicked.connect(self._open_recorder)
        for b in (b_viz, b_rec):
            b.setMinimumHeight(46)
            v.addWidget(b)

        self.resize(320, 230)

    def _open_viz(self) -> None:
        from growth_viz.main_window import MainWindow as VizWindow
        w = VizWindow()
        self._windows.append(w)
        w.show()
        self.close()

    def _open_recorder(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Новая или существующая база", "experiment.db", "SQLite (*.db)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not path:
            return
        from recorder.db import RecordingDB
        from recorder.record_window import RecordWindow
        w = RecordWindow(RecordingDB(path))
        self._windows.append(w)
        w.show()
        self.close()


def _selftest() -> int:
    """Проверить, что упаковано всё для .xlsx: запись → чтение сходятся."""
    import tempfile
    from pathlib import Path

    import pandas as pd

    from growth_viz.loader import load_sample
    from growth_viz.writer import write_sample

    d = Path(tempfile.mkdtemp())
    p = write_sample(
        d / "selftest.xlsx",
        {"sample_name": "st", "start_date": "2026-01-01 00:00"},
        pd.DataFrame({"time_h": [0.0, 1.0, 2.0], "OD600": [0.1, 0.3, 0.9]}),
    )
    s = load_sample(p)
    ok = s.value_columns == ["OD600"] and list(s.data["OD600"]) == [0.1, 0.3, 0.9]
    print("SELFTEST", "OK" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    app = QApplication(sys.argv)
    launcher = Launcher()
    launcher.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
