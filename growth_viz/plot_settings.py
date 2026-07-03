"""Настройки внешнего вида графика."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PlotSettings:
    """Параметры оформления графика, управляемые из панели настроек."""

    # --- точки / маркеры ---
    show_markers: bool = False
    marker_style: str = "o"      # matplotlib-код маркера
    marker_size: float = 4.0

    # --- линии ---
    mean_linewidth: float = 2.2
    individual_alpha: float = 0.35
    band_alpha: float = 0.18

    # --- шрифт ---
    font_family: str = "DejaVu Sans"
    font_size: int = 10

    # --- оси ---
    x_tick_step: float = 0.0     # 0 = автоматически
    y_tick_step: float = 0.0     # 0 = автоматически
    show_grid: bool = True
    grid_alpha: float = 0.3

    # --- прочее ---
    show_legend: bool = True
    title: str = ""

    # --- размер фигуры и экспорт ---
    fig_width_in: float = 4.72    # ширина, дюймы (~12 см)
    fig_height_in: float = 3.15   # высота, дюймы (~8 см)
    export_dpi: int = 300

    @property
    def aspect_ratio(self) -> float:
        """Соотношение сторон ширина/высота."""
        return self.fig_width_in / self.fig_height_in if self.fig_height_in else 1.0
