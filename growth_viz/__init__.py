"""growth_viz — визуализация экспериментальных кривых роста из Excel-файлов."""

from .model import Sample
from .loader import load_folder, load_sample, common_meta_keys
from .grouping import Group, group_samples, aggregate
from .alignment import apply_alignment, clear_alignment, THRESHOLD, MAX_RATE
from .writer import write_sample

__all__ = [
    "Sample",
    "load_folder",
    "load_sample",
    "common_meta_keys",
    "Group",
    "group_samples",
    "aggregate",
    "apply_alignment",
    "clear_alignment",
    "THRESHOLD",
    "MAX_RATE",
    "write_sample",
]
