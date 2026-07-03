"""Запуск приложения визуализации кривых роста.

Использование:
    python main.py [папка_с_xlsx]

Если папка не указана, при наличии открывается test_data.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from growth_viz.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    win = MainWindow()

    # Начальная папка: аргумент командной строки или test_data по умолчанию.
    start = None
    if len(sys.argv) > 1:
        start = sys.argv[1]
    else:
        default = Path(__file__).parent / "test_data"
        if default.exists():
            start = str(default)
    if start:
        win.load_folder(start)

    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
