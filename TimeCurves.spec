# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-спек: один исполняемый лаунчер (визуализатор + запись).

Собирается на каждой ОС отдельно (кросс-компиляция GUI невозможна).
На macOS дополнительно собирается .app-бандл.
"""

import sys

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# openpyxl подключается pandas'ом динамически (по строке engine="openpyxl"),
# прямого import нет — поэтому включаем его явно, иначе .xlsx не заработает.
hiddenimports = (
    ["matplotlib.backends.backend_qt5agg", "et_xmlfile"]
    + collect_submodules("openpyxl")
)
datas = collect_data_files("matplotlib")
binaries = []

# Принудительно собираем весь PyQt5 (QtCore/QtGui/QtWidgets + Qt5-DLL и плагины).
# Без этого на некоторых сборках .pyd/.dll не попадают в бандл и на Windows
# получаем "No module named PyQt5.QtCore".
_pyqt5_datas, _pyqt5_binaries, _pyqt5_hidden = collect_all("PyQt5")
datas += _pyqt5_datas
binaries += _pyqt5_binaries
hiddenimports += _pyqt5_hidden

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt6", "PySide2", "PySide6", "scipy", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TimeCurves",
    debug=False,
    strip=False,
    upx=False,
    console=False,          # GUI-приложение, без консоли
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="TimeCurves",
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="TimeCurves.app",
        bundle_identifier="ru.timecurves.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleDisplayName": "Кривые роста",
        },
    )
