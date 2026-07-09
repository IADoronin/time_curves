"""Холст matplotlib для отрисовки кривых по группам."""

from __future__ import annotations

import matplotlib as mpl
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.ticker import MultipleLocator
from PyQt6.QtWidgets import QWidget

from .grouping import Group, aggregate
from .plot_settings import PlotSettings

# Палитра, дружелюбная к дальтоникам (Okabe-Ito).
PALETTE = [
    "#0072B2", "#D55E00", "#009E73", "#CC79A7",
    "#E69F00", "#56B4E9", "#F0E442", "#000000",
]


class PlotCanvas(FigureCanvasQTAgg):
    """Виджет-график: рисует группы образцов для выбранной величины."""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(6, 4), layout="constrained")
        super().__init__(self.fig)
        self.setParent(parent)
        self.ax = self.fig.add_subplot(111)
        self._settings = PlotSettings()  # последние применённые настройки

    @staticmethod
    def _rc_for(st: PlotSettings) -> dict:
        """rcParams для согласованного применения шрифта (в т.ч. к подписям осей)."""
        return {
            "font.family": st.font_family,
            "font.size": st.font_size,
            "axes.titlesize": st.font_size,
            "axes.labelsize": st.font_size,
            "xtick.labelsize": st.font_size,
            "ytick.labelsize": st.font_size,
            "legend.fontsize": st.font_size,
        }

    def plot_groups(
        self,
        groups: list[Group],
        value_col: str,
        show_mean: bool = True,
        show_band: bool = True,
        show_individual: bool = True,
        settings: PlotSettings | None = None,
    ) -> None:
        """Отрисовать список групп для одной измеряемой величины.

        show_mean       — линия среднего по повторам
        show_band       — заливка ±1 SD вокруг среднего
        show_individual — тонкие линии отдельных повторов
        settings        — параметры оформления (маркеры, шрифт, оси…)
        """
        st = settings or PlotSettings()
        self._settings = st
        marker = st.marker_style if st.show_markers else ""

        with mpl.rc_context(self._rc_for(st)):
            self.ax.clear()

            for i, g in enumerate(groups):
                color = PALETTE[i % len(PALETTE)]

                if show_individual:
                    for s in g.samples:
                        if not s.enabled or value_col not in s.data.columns:
                            continue
                        self.ax.plot(
                            s.times(), s.data[value_col],
                            color=color, alpha=st.individual_alpha, linewidth=1.0,
                            marker=marker, markersize=st.marker_size, zorder=1,
                        )

                if show_mean or show_band:
                    agg = aggregate(g, value_col)
                    if agg.empty:
                        continue
                    if show_band:
                        self.ax.fill_between(
                            agg["time"], agg["mean"] - agg["std"], agg["mean"] + agg["std"],
                            color=color, alpha=st.band_alpha, zorder=2, linewidth=0,
                        )
                    if show_mean:
                        n = int(agg["n"].max()) if len(agg) else 0
                        self.ax.plot(
                            agg["time"], agg["mean"],
                            color=color, linewidth=st.mean_linewidth,
                            marker=marker, markersize=st.marker_size, zorder=3,
                            label=f"{g.label} (n={n})",
                        )

            ref = groups[0].samples[0] if groups and groups[0].samples else None
            self.ax.set_xlabel(self._x_label(ref))
            self.ax.set_ylabel(value_col)
            if st.title:
                self.ax.set_title(st.title)

            # Ось дат: авто-локатор/форматтер вместо числового шага.
            dates_axis = ref is not None and ref.is_datetime_time and ref.time_mode == "dates"
            if dates_axis:
                import matplotlib.dates as mdates
                loc = mdates.AutoDateLocator()
                self.ax.xaxis.set_major_locator(loc)
                self.ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
            elif st.x_tick_step > 0:
                self.ax.xaxis.set_major_locator(MultipleLocator(st.x_tick_step))
            if st.y_tick_step > 0:
                self.ax.yaxis.set_major_locator(MultipleLocator(st.y_tick_step))

            self.ax.grid(st.show_grid, alpha=st.grid_alpha)

            handles, _ = self.ax.get_legend_handles_labels()
            if handles and st.show_legend:
                self.ax.legend(title=groups[0].key if groups else "", frameon=False)

            self.draw()

    @staticmethod
    def _x_label(ref) -> str:
        """Подпись оси X в зависимости от типа времени и режима."""
        if ref is None:
            return "time"
        if ref.is_datetime_time:
            return "дата" if ref.time_mode == "dates" else "часы от старта"
        return ref.time_column

    def export(self, path: str, settings: PlotSettings | None = None) -> None:
        """Сохранить текущий график в файл с заданными размером и DPI.

        Формат определяется по расширению файла (png/pdf/svg/tif/eps).
        Размер фигуры и DPI берутся из settings; шрифты применяются через
        rc_context, чтобы файл точно совпадал с настройками на экране.
        """
        st = settings or self._settings
        old_size = self.fig.get_size_inches().copy()
        with mpl.rc_context(self._rc_for(st)):
            self.fig.set_size_inches(st.fig_width_in, st.fig_height_in)
            self.fig.savefig(path, dpi=st.export_dpi)
            self.fig.set_size_inches(old_size)
        self.draw_idle()


class AspectContainer(QWidget):
    """Контейнер, удерживающий холст в заданном соотношении сторон (letterbox).

    При ``ratio=None`` холст заполняет всю область; иначе вписывается
    прямоугольником нужных пропорций по центру — предпросмотр «как при экспорте».
    """

    def __init__(self, canvas: FigureCanvasQTAgg, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        canvas.setParent(self)
        self.ratio: float | None = None

    def set_ratio(self, ratio: float | None) -> None:
        self.ratio = ratio if (ratio and ratio > 0) else None
        self._relayout()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._relayout()

    def _relayout(self) -> None:
        W, H = self.width(), self.height()
        if not self.ratio:
            self.canvas.setGeometry(0, 0, W, H)
            return
        if W / H > self.ratio:      # область шире нужного — ограничиваем по высоте
            h = H
            w = int(round(h * self.ratio))
        else:                        # область у́же — ограничиваем по ширине
            w = W
            h = int(round(w / self.ratio))
        self.canvas.setGeometry((W - w) // 2, (H - h) // 2, w, h)
