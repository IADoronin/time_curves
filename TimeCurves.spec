# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller-спек: один исполняемый лаунчер (визуализатор + запись).

Собирается на каждой ОС отдельно (кросс-компиляция GUI невозможна).
На macOS дополнительно собирается .app-бандл.
"""

import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# openpyxl подключается pandas'ом динамически (по строке engine="openpyxl"),
# прямого import нет — поэтому включаем его явно, иначе .xlsx не заработает.
hiddenimports = (
    ["matplotlib.backends.backend_qtagg", "et_xmlfile"]
    + collect_submodules("openpyxl")
)
datas = collect_data_files("matplotlib")

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "PyQt5", "PySide2", "PySide6", "scipy", "IPython", "pytest"],
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
