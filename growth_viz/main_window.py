"""Главное окно приложения визуализации кривых роста."""

from __future__ import annotations

from pathlib import Path

from matplotlib.backends.backend_qtagg import NavigationToolbar2QT
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .alignment import MAX_RATE, THRESHOLD, apply_alignment, clear_alignment
from .grouping import group_samples
from .loader import common_meta_keys, load_folder
from .model import Sample
from .plot_canvas import AspectContainer, PlotCanvas
from .settings_panel import SettingsPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Кривые роста — визуализация")
        self.resize(1100, 680)

        self.samples: list[Sample] = []
        self._updating = False  # защита от рекурсии при программном изменении дерева

        self._build_ui()

    # ---------- построение интерфейса ----------
    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- левая панель управления ---
        panel = QWidget()
        pv = QVBoxLayout(panel)

        self.open_btn = QPushButton("Открыть папку…")
        self.open_btn.clicked.connect(self.open_folder)
        pv.addWidget(self.open_btn)

        self.folder_lbl = QLabel("Папка не выбрана")
        self.folder_lbl.setWordWrap(True)
        self.folder_lbl.setStyleSheet("color: gray;")
        pv.addWidget(self.folder_lbl)

        form = QFormLayout()
        self.group_combo = QComboBox()
        self.group_combo.currentTextChanged.connect(self._on_group_changed)
        form.addRow("Группировать по:", self.group_combo)

        self.value_combo = QComboBox()
        self.value_combo.currentTextChanged.connect(self._replot)
        form.addRow("Показатель:", self.value_combo)
        pv.addLayout(form)

        # --- опции отображения ---
        disp = QGroupBox("Отображение")
        dv = QVBoxLayout(disp)
        self.cb_mean = QCheckBox("Среднее по повторам")
        self.cb_band = QCheckBox("Полоса ±1 SD")
        self.cb_indiv = QCheckBox("Отдельные повторы")
        for cb in (self.cb_mean, self.cb_band, self.cb_indiv):
            cb.setChecked(True)
            cb.stateChanged.connect(self._replot)
            dv.addWidget(cb)
        # Ось X: часы от старта или абсолютные даты (актуально для datetime-данных).
        axis_row = QFormLayout()
        self.axis_combo = QComboBox()
        self.axis_combo.addItem("Часы от старта", "elapsed")
        self.axis_combo.addItem("Даты", "dates")
        self.axis_combo.currentIndexChanged.connect(self._replot)
        axis_row.addRow("Ось X:", self.axis_combo)
        dv.addLayout(axis_row)
        pv.addWidget(disp)

        # --- коррекция сдвига времени (выравнивание) ---
        align = QGroupBox("Коррекция сдвига времени")
        af = QFormLayout(align)
        self.cb_align = QCheckBox("Выравнивать кривые")
        self.cb_align.stateChanged.connect(self._replot)
        af.addRow(self.cb_align)

        self.align_method = QComboBox()
        self.align_method.addItem("По уровню сигнала", THRESHOLD)
        self.align_method.addItem("По макс. скорости роста", MAX_RATE)
        self.align_method.currentIndexChanged.connect(self._on_align_method)
        af.addRow("Метод:", self.align_method)

        self.align_ref = QComboBox()  # опорный показатель (заполняется при загрузке)
        self.align_ref.currentIndexChanged.connect(self._replot)
        af.addRow("Опорный:", self.align_ref)

        self.align_level = QDoubleSpinBox()
        self.align_level.setRange(0.0, 1e6)
        self.align_level.setDecimals(3)
        self.align_level.setSingleStep(0.05)
        self.align_level.setValue(0.2)
        self.align_level.valueChanged.connect(self._replot)
        self.lbl_level = QLabel("Уровень:")
        af.addRow(self.lbl_level, self.align_level)
        pv.addWidget(align)

        # --- дерево образцов с чекбоксами ---
        pv.addWidget(QLabel("Образцы (сними галку — уберётся с графика):"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemChanged.connect(self._on_item_changed)
        pv.addWidget(self.tree, stretch=1)

        splitter.addWidget(panel)

        # --- правая часть: график ---
        right = QWidget()
        rv = QVBoxLayout(right)
        self.canvas = PlotCanvas(right)
        self.aspect = AspectContainer(self.canvas, right)
        self.toolbar = NavigationToolbar2QT(self.canvas, right)
        rv.addWidget(self.toolbar)
        rv.addWidget(self.aspect, stretch=1)
        splitter.addWidget(right)

        # --- правая колонка: настройки графика (в прокрутке) ---
        self.settings_panel = SettingsPanel()
        self.settings_panel.changed.connect(self._replot)
        self.settings_panel.export_requested.connect(self._export)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.settings_panel)
        scroll.setMinimumWidth(300)
        splitter.addWidget(scroll)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([290, 600, 310])
        self.setCentralWidget(splitter)

    # ---------- загрузка ----------
    def open_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку с .xlsx")
        if folder:
            self.load_folder(folder)

    def load_folder(self, folder: str | Path) -> None:
        self.samples = load_folder(folder)
        self.folder_lbl.setText(f"{folder}  —  образцов: {len(self.samples)}")
        self.folder_lbl.setStyleSheet("color: black;")
        self._populate_controls()

    def _populate_controls(self) -> None:
        self._updating = True
        # ключи группировки
        self.group_combo.clear()
        keys = common_meta_keys(self.samples)
        self.group_combo.addItems(keys)
        # показатели (объединение колонок величин)
        cols: list[str] = []
        for s in self.samples:
            for c in s.value_columns:
                if c not in cols:
                    cols.append(c)
        self.value_combo.clear()
        self.value_combo.addItems(cols)
        # опорный показатель для выравнивания — те же колонки (по умолч. первая)
        self.align_ref.clear()
        self.align_ref.addItems(cols)
        self._updating = False

        self._rebuild_tree()
        self._replot()

    def _on_align_method(self) -> None:
        # уровень нужен только методу «По уровню сигнала»
        is_threshold = self.align_method.currentData() == THRESHOLD
        self.lbl_level.setVisible(is_threshold)
        self.align_level.setVisible(is_threshold)
        self._replot()

    # ---------- дерево образцов ----------
    def _rebuild_tree(self) -> None:
        self._updating = True
        self.tree.clear()
        key = self.group_combo.currentText()
        if key and self.samples:
            for g in group_samples(self.samples, key, only_enabled=False):
                top = QTreeWidgetItem([f"{key} = {g.value}"])
                top.setFlags(top.flags() | Qt.ItemFlag.ItemIsUserCheckable
                             | Qt.ItemFlag.ItemIsAutoTristate)
                self.tree.addTopLevelItem(top)
                for s in g.samples:
                    child = QTreeWidgetItem([s.name])
                    child.setFlags(child.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                    child.setCheckState(
                        0,
                        Qt.CheckState.Checked if s.enabled else Qt.CheckState.Unchecked,
                    )
                    child.setData(0, Qt.ItemDataRole.UserRole, s)
                    top.addChild(child)
                top.setExpanded(True)
        self._updating = False

    def _on_item_changed(self, item: QTreeWidgetItem, _col: int) -> None:
        if self._updating:
            return
        s = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(s, Sample):
            s.enabled = item.checkState(0) == Qt.CheckState.Checked
            self._replot()

    # ---------- реакции ----------
    def _on_group_changed(self, _text: str) -> None:
        if self._updating:
            return
        self._rebuild_tree()
        self._replot()

    def _replot(self, *_args) -> None:
        if self._updating or not self.samples:
            return
        key = self.group_combo.currentText()
        value_col = self.value_combo.currentText()
        if not key or not value_col:
            return
        # Режим оси X (часы от старта / даты) для всех образцов.
        mode = self.axis_combo.currentData()
        for s in self.samples:
            s.time_mode = mode
        # Коррекция сдвига времени до группировки/усреднения.
        if self.cb_align.isChecked():
            apply_alignment(
                self.samples,
                ref_col=self.align_ref.currentText(),
                method=self.align_method.currentData(),
                level=self.align_level.value(),
                group_key=key,
            )
        else:
            clear_alignment(self.samples)

        groups = group_samples(self.samples, key, only_enabled=True)
        groups = [g for g in groups if any(s.enabled for s in g.samples)]
        settings = self.settings_panel.to_settings()
        self.canvas.plot_groups(
            groups,
            value_col,
            show_mean=self.cb_mean.isChecked(),
            show_band=self.cb_band.isChecked(),
            show_individual=self.cb_indiv.isChecked(),
            settings=settings,
        )
        # Предпросмотр в пропорциях экспорта (letterbox) или на всю область.
        lock = self.settings_panel.cb_lock_aspect.isChecked()
        self.aspect.set_ratio(settings.aspect_ratio if lock else None)

    def _export(self) -> None:
        """Сохранить график в файл с текущими размером/DPI/форматом."""
        if not self.samples:
            return
        ext = self.settings_panel.current_ext()
        filters = {
            "png": "PNG (*.png)", "pdf": "PDF (*.pdf)", "svg": "SVG (*.svg)",
            "tif": "TIFF (*.tif *.tiff)", "eps": "EPS (*.eps)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить график", f"figure.{ext}", filters.get(ext, "")
        )
        if not path:
            return
        try:
            self.canvas.export(path, self.settings_panel.to_settings())
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Ошибка экспорта", str(exc))
            return
        self.statusBar().showMessage(f"Сохранено: {path}", 5000)
