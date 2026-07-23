"""Запуск приложения записи кривых.

Использование:
    python record.py [база.db]

Если путь не указан, откроется диалог создания/выбора базы SQLite.
"""

from __future__ import annotations

import sys

from PyQt5.QtWidgets import QApplication, QFileDialog

from recorder.db import RecordingDB
from recorder.record_window import RecordWindow


def main() -> int:
    app = QApplication(sys.argv)

    db = None
    if len(sys.argv) > 1:
        db = RecordingDB(sys.argv[1])
    else:
        path, _ = QFileDialog.getSaveFileName(
            None, "Новая или существующая база", "experiment.db", "SQLite (*.db)",
            options=QFileDialog.DontConfirmOverwrite,
        )
        if path:
            db = RecordingDB(path)

    win = RecordWindow(db)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
