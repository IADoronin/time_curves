"""Панель настроек оформления графика (правая колонка)."""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .plot_settings import PlotSettings

CM_PER_INCH = 2.54

# Стили маркеров: подпись -> код matplotlib.
MARKERS = [
    ("Круг ●", "o"),
    ("Квадрат ■", "s"),
    ("Треугольник ▲", "^"),
    ("Ромб ◆", "D"),
    ("Крест ✕", "x"),
    ("Плюс +", "+"),
    ("Точка ·", "."),
]

# Шрифты, которые гарантированно рендерятся (без предупреждений matplotlib).
FONT_FAMILIES = [
    "DejaVu Sans",
    "DejaVu Serif",
    "DejaVu Sans Mono",
    "sans-serif",
    "serif",
    "monospace",
]


EXPORT_FORMATS = ["PNG", "PDF", "SVG", "TIFF", "EPS"]
FORMAT_EXT = {"PNG": "png", "PDF": "pdf", "SVG": "svg", "TIFF": "tif", "EPS": "eps"}


class SettingsPanel(QWidget):
    """Набор контролов оформления. Испускает ``changed`` при любом изменении."""

    changed = pyqtSignal()
    export_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()
        self._update_export_info()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)

        # --- Точки / маркеры ---
        g_mark = QGroupBox("Точки")
        f = self._form(g_mark)
        self.cb_markers = QCheckBox("Показывать точки")
        self.cb_markers.stateChanged.connect(self.changed)
        f.addRow(self.cb_markers)

        self.cmb_marker = QComboBox()
        for label, code in MARKERS:
            self.cmb_marker.addItem(label, code)
        self.cmb_marker.currentIndexChanged.connect(self.changed)
        f.addRow("Стиль:", self.cmb_marker)

        self.sp_marker_size = self._dspin(1.0, 20.0, 0.5, 4.0)
        f.addRow("Размер точек:", self.sp_marker_size)
        root.addWidget(g_mark)

        # --- Линии ---
        g_line = QGroupBox("Линии")
        f = self._form(g_line)
        self.sp_mean_lw = self._dspin(0.5, 8.0, 0.1, 2.2)
        f.addRow("Толщина среднего:", self.sp_mean_lw)
        self.sp_indiv_alpha = self._dspin(0.0, 1.0, 0.05, 0.35)
        f.addRow("Прозрачн. повторов:", self.sp_indiv_alpha)
        self.sp_band_alpha = self._dspin(0.0, 1.0, 0.05, 0.18)
        f.addRow("Прозрачн. полосы SD:", self.sp_band_alpha)
        root.addWidget(g_line)

        # --- Шрифт ---
        g_font = QGroupBox("Шрифт")
        f = self._form(g_font)
        self.cmb_font = QComboBox()
        self.cmb_font.addItems(FONT_FAMILIES)
        self.cmb_font.currentIndexChanged.connect(self.changed)
        f.addRow("Семейство:", self.cmb_font)
        self.sp_font = QSpinBox()
        self.sp_font.setRange(6, 32)
        self.sp_font.setValue(10)
        self.sp_font.valueChanged.connect(self.changed)
        f.addRow("Размер:", self.sp_font)
        root.addWidget(g_font)

        # --- Оси ---
        g_axes = QGroupBox("Оси")
        f = self._form(g_axes)
        self.sp_xstep = self._dspin(0.0, 1000.0, 1.0, 0.0)
        self.sp_xstep.setSpecialValueText("авто")  # 0 -> "авто"
        f.addRow("Шаг X:", self.sp_xstep)
        self.sp_ystep = self._dspin(0.0, 1000.0, 0.1, 0.0)
        self.sp_ystep.setSpecialValueText("авто")
        f.addRow("Шаг Y:", self.sp_ystep)
        self.cb_grid = QCheckBox("Сетка")
        self.cb_grid.setChecked(True)
        self.cb_grid.stateChanged.connect(self.changed)
        f.addRow(self.cb_grid)
        root.addWidget(g_axes)

        # --- Прочее ---
        g_misc = QGroupBox("Прочее")
        f = self._form(g_misc)
        self.cb_legend = QCheckBox("Легенда")
        self.cb_legend.setChecked(True)
        self.cb_legend.stateChanged.connect(self.changed)
        f.addRow(self.cb_legend)
        self.ed_title = QLineEdit()
        self.ed_title.setPlaceholderText("(без заголовка)")
        self.ed_title.textChanged.connect(self.changed)
        f.addRow("Заголовок:", self.ed_title)
        root.addWidget(g_misc)

        # --- Экспорт (для статей) ---
        g_exp = QGroupBox("Экспорт")
        f = self._form(g_exp)

        self.cmb_unit = QComboBox()
        self.cmb_unit.addItems(["см", "дюйм"])
        self.cmb_unit.currentIndexChanged.connect(self._on_unit_changed)
        f.addRow("Единицы:", self.cmb_unit)

        # Значения хранятся/вводятся в текущих единицах; старт — см.
        self.sp_width = self._dspin(1.0, 100.0, 0.5, 12.0)
        f.addRow("Ширина:", self.sp_width)
        self.sp_height = self._dspin(1.0, 100.0, 0.5, 8.0)
        f.addRow("Высота:", self.sp_height)

        self.sp_dpi = QSpinBox()
        self.sp_dpi.setRange(50, 1200)
        self.sp_dpi.setSingleStep(50)
        self.sp_dpi.setValue(300)
        self.sp_dpi.valueChanged.connect(self.changed)
        self.sp_dpi.valueChanged.connect(self._update_export_info)
        f.addRow("DPI:", self.sp_dpi)

        self.cmb_format = QComboBox()
        self.cmb_format.addItems(EXPORT_FORMATS)
        f.addRow("Формат:", self.cmb_format)

        self.cb_lock_aspect = QCheckBox("Предпросмотр в этих пропорциях")
        self.cb_lock_aspect.stateChanged.connect(self.changed)
        f.addRow(self.cb_lock_aspect)

        self.lbl_export_info = QLabel()
        self.lbl_export_info.setStyleSheet("color: gray;")
        self.lbl_export_info.setWordWrap(True)
        f.addRow(self.lbl_export_info)

        self.btn_export = QPushButton("Сохранить график…")
        self.btn_export.clicked.connect(self.export_requested)
        f.addRow(self.btn_export)

        # Пересчёт инфо-строки и предпросмотра при смене размера.
        self.sp_width.valueChanged.connect(self._update_export_info)
        self.sp_height.valueChanged.connect(self._update_export_info)
        root.addWidget(g_exp)

        root.addStretch(1)

    def _form(self, parent) -> QFormLayout:
        """QFormLayout, где длинные подписи переносятся, а поля тянутся по ширине.

        Это не даёт обрезаться длинным подписям в узкой правой колонке.
        """
        f = QFormLayout(parent)
        f.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        return f

    def _dspin(self, lo: float, hi: float, step: float, val: float) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setRange(lo, hi)
        sp.setSingleStep(step)
        sp.setValue(val)
        sp.setDecimals(2)
        sp.valueChanged.connect(self.changed)
        return sp

    # ---------- размер / экспорт ----------
    def _unit_is_cm(self) -> bool:
        return self.cmb_unit.currentText() == "см"

    def _to_inches(self, value: float) -> float:
        return value / CM_PER_INCH if self._unit_is_cm() else value

    def width_in(self) -> float:
        return self._to_inches(self.sp_width.value())

    def height_in(self) -> float:
        return self._to_inches(self.sp_height.value())

    def current_ext(self) -> str:
        return FORMAT_EXT[self.cmb_format.currentText()]

    def _on_unit_changed(self) -> None:
        """Пересчитать ширину/высоту так, чтобы физический размер не менялся."""
        to_cm = self._unit_is_cm()  # True: дюйм->см, False: см->дюйм
        factor = CM_PER_INCH if to_cm else 1.0 / CM_PER_INCH
        for sp in (self.sp_width, self.sp_height):
            sp.blockSignals(True)
            sp.setValue(sp.value() * factor)
            sp.blockSignals(False)
        self._update_export_info()
        self.changed.emit()

    def _update_export_info(self) -> None:
        w_in, h_in = self.width_in(), self.height_in()
        dpi = self.sp_dpi.value()
        px_w, px_h = round(w_in * dpi), round(h_in * dpi)
        ratio = w_in / h_in if h_in else 0.0
        self.lbl_export_info.setText(
            f"{px_w}×{px_h} px  ·  {w_in * CM_PER_INCH:.1f}×{h_in * CM_PER_INCH:.1f} см"
            f"  ·  {ratio:.2f}:1"
        )

    def to_settings(self) -> PlotSettings:
        """Собрать текущее состояние контролов в PlotSettings."""
        return PlotSettings(
            show_markers=self.cb_markers.isChecked(),
            marker_style=self.cmb_marker.currentData(),
            marker_size=self.sp_marker_size.value(),
            mean_linewidth=self.sp_mean_lw.value(),
            individual_alpha=self.sp_indiv_alpha.value(),
            band_alpha=self.sp_band_alpha.value(),
            font_family=self.cmb_font.currentText(),
            font_size=self.sp_font.value(),
            x_tick_step=self.sp_xstep.value(),
            y_tick_step=self.sp_ystep.value(),
            show_grid=self.cb_grid.isChecked(),
            show_legend=self.cb_legend.isChecked(),
            title=self.ed_title.text().strip(),
            fig_width_in=self.width_in(),
            fig_height_in=self.height_in(),
            export_dpi=self.sp_dpi.value(),
        )
