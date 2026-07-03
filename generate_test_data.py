"""
Генератор тестовых Excel-файлов с данными экспериментов (кривые роста).

Каждый файл содержит два листа:
  - meta : условия эксперимента, извлечённые из имени файла + дата старта
  - data : временные ряды измеряемых величин (OD600, pH, субстрат)

Имя файла кодирует условия по схеме:
    {aeration}_{co2}_{substrate}_{replicate}
Например: aero_with_co2_malate_1
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).parent / "test_data"

# Базовая дата старта; для каждого повтора смещаем на несколько дней,
# чтобы даты были разными и осмысленными.
BASE_START = datetime(2026, 5, 12, 10, 0)

# Список имён файлов, которые нужно сгенерировать.
SAMPLE_NAMES = [
    "aero_with_co2_malate_1",
    "aero_with_co2_malate_2",
    "aero_with_co2_malate_3",
    "aero_with_co2_acetate_1",
    "aero_with_co2_acetate_2",
    "aero_with_co2_acetate_3",
]


def parse_meta_from_name(name: str) -> dict:
    """Извлечь условия эксперимента из имени файла.

    Возвращает словарь с человекочитаемыми условиями.
    Устойчив к вариантам написания (co2 / co_2).
    """
    # Нормализуем 'co_2' -> 'co2', приводим к нижнему регистру.
    norm = name.lower().replace("co_2", "co2")
    tokens = norm.split("_")

    # --- Аэрация ---
    if "anaero" in norm:
        aeration = "anaerobic"
    elif "aero" in norm:
        aeration = "aerobic"
    else:
        aeration = "unknown"

    # --- CO2 ---
    if "with_co2" in norm or "with" in tokens and "co2" in tokens:
        co2 = "CO2+"
    elif "no_co2" in norm or "without" in norm:
        co2 = "CO2-"
    else:
        co2 = "unknown"

    # --- Субстрат ---
    known_substrates = ["malate", "acetate", "succinate", "glucose", "lactate", "pyruvate"]
    substrate = next((s for s in known_substrates if s in tokens), "unknown")

    # --- Номер повтора (замыкающее число) ---
    m = re.search(r"(\d+)$", name)
    replicate = int(m.group(1)) if m else None

    return {
        "aeration": aeration,
        "co2": co2,
        "substrate": substrate,
        "replicate": replicate,
    }


def gompertz(t: np.ndarray, A: float, mu: float, lag: float) -> np.ndarray:
    """Модель роста Гомпертца для OD600.

    A   - асимптота (максимальная OD)
    mu  - максимальная удельная скорость роста
    lag - лаг-фаза (ч)
    """
    e = np.e
    return A * np.exp(-np.exp((mu * e / A) * (lag - t) + 1.0))


def make_data(meta: dict, seed: int) -> pd.DataFrame:
    """Сгенерировать временные ряды измерений для одного эксперимента."""
    rng = np.random.default_rng(seed)

    # Параметры роста зависят от субстрата.
    if meta["substrate"] == "malate":
        A, mu, lag = 1.35, 0.14, 4.0      # малат: быстрее и выше
        s0 = 20.0                          # начальная концентрация субстрата, мМ
    elif meta["substrate"] == "acetate":
        A, mu, lag = 0.85, 0.08, 7.0      # ацетат: медленнее и ниже
        s0 = 20.0
    else:
        A, mu, lag = 1.0, 0.10, 5.0
        s0 = 20.0

    # Небольшой разброс между повторами.
    A *= 1 + rng.normal(0, 0.04)
    mu *= 1 + rng.normal(0, 0.06)
    lag *= 1 + rng.normal(0, 0.08)

    # Неверно определённая нулевая точка: реальный «ноль» культуры не совпадает
    # с записанным, поэтому кривые сдвинуты друг относительно друга по времени.
    t_shift = rng.normal(0.0, 4.0)  # ч, ± ~4 ч (заметная рассинхронизация)

    # Ровно 7 измерений по реалистичной схеме: часто в начале (фаза роста),
    # реже к концу (плато) — интервалы растут. Степенное распределение по
    # времени + лёгкая нерегулярность; старт не ровно в нуле, конец плавает.
    n_points = 7
    t_start = rng.uniform(0.0, 0.8)
    t_end = rng.uniform(46.0, 50.0)
    p = rng.uniform(1.5, 1.9)  # >1 → сгущение к началу
    frac = (np.arange(n_points) / (n_points - 1)) ** p  # 0..1, растущие интервалы
    t = t_start + frac * (t_end - t_start)
    t[1:-1] += rng.normal(0, 0.4, size=n_points - 2)  # нерегулярность (края фиксируем)
    t = np.round(np.sort(t), 2)

    # OD считаем по «истинному» (сдвинутому) времени — отсюда сдвиг кривых.
    od = gompertz(t - t_shift, A, mu, lag)
    od = np.clip(od + rng.normal(0, 0.015, size=t.shape), 0.02, None)

    # pH слегка снижается по мере роста (подкисление среды).
    ph = 7.1 - 0.6 * (od / A) + rng.normal(0, 0.02, size=t.shape)

    # Субстрат расходуется пропорционально приросту биомассы.
    od0 = od.min()
    consumed = s0 * (od - od0) / (A - od0 + 1e-9)
    substrate = np.clip(s0 - consumed, 0, s0) + rng.normal(0, 0.2, size=t.shape)
    substrate = np.clip(substrate, 0, None)

    print(f"      сдвиг t0 = {t_shift:+.2f} ч, точек = {len(t)}, "
          f"интервал {np.diff(t).min():.2f}–{np.diff(t).max():.2f} ч")

    return pd.DataFrame(
        {
            "time_h": t,
            "OD600": np.round(od, 4),
            "pH": np.round(ph, 3),
            "substrate_mM": np.round(substrate, 3),
        }
    )


def make_meta_frame(meta: dict, start: datetime, source_name: str) -> pd.DataFrame:
    """Оформить meta как двухколоночную таблицу parameter/value."""
    rows = [
        ("sample_name", source_name),
        ("start_date", start.strftime("%Y-%m-%d %H:%M")),
        ("aeration", meta["aeration"]),
        ("co2", meta["co2"]),
        ("substrate", meta["substrate"]),
        ("replicate", meta["replicate"]),
    ]
    return pd.DataFrame(rows, columns=["parameter", "value"])


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)

    for i, name in enumerate(SAMPLE_NAMES):
        meta = parse_meta_from_name(name)
        start = BASE_START + timedelta(days=i)  # разные даты старта
        meta_df = make_meta_frame(meta, start, name)
        data_df = make_data(meta, seed=1000 + i)

        out_path = OUT_DIR / f"{name}.xlsx"
        with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
            meta_df.to_excel(xw, sheet_name="meta", index=False)
            data_df.to_excel(xw, sheet_name="data", index=False)

        print(f"[ok] {out_path.name}: {meta}  start={start:%Y-%m-%d}")


if __name__ == "__main__":
    main()
