"""Слой SQLite для записи кривых + экспорт в Excel.

Один файл .db = один эксперимент: общая схема (свойства-условия и измеряемые
величины) + много кривых. Каждая кривая экспортируется в отдельный .xlsx,
совместимый с визуализатором (growth_viz).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from growth_viz.writer import write_sample

# Единицы времени -> имя колонки в листе data и коэффициент перевода из часов.
TIME_UNITS = ("h", "min", "d")
TIME_COLUMN = {"h": "time_h", "min": "time_min", "d": "time_d"}
_HOURS_TO_UNIT = {"h": 1.0, "min": 60.0, "d": 1.0 / 24.0}

# Столбец абсолютной даты+времени в экспортируемом листе data.
DATETIME_COLUMN = "datetime"

# Три независимых цветных флага (битовая маска).
FLAG_COUNT = 3
FLAG_LABELS = ("🔴", "🟡", "🟢")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS properties (
    id       INTEGER PRIMARY KEY,
    name     TEXT UNIQUE NOT NULL,
    kind     TEXT NOT NULL CHECK (kind IN ('enum','numeric')),
    options  TEXT,               -- JSON-список вариантов для enum
    unit     TEXT,
    position INTEGER NOT NULL,
    min_val  REAL,               -- ограничение numeric: нижняя граница
    max_val  REAL                -- ограничение numeric: верхняя граница
);
CREATE TABLE IF NOT EXISTS measured_vars (
    id       INTEGER PRIMARY KEY,
    name     TEXT UNIQUE NOT NULL,
    unit     TEXT,
    position INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS curves (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    start_iso   TEXT NOT NULL,
    finished    INTEGER NOT NULL DEFAULT 0,
    created_iso TEXT NOT NULL,
    flags       INTEGER NOT NULL DEFAULT 0   -- битовая маска цветных тегов
);
CREATE TABLE IF NOT EXISTS curve_meta (
    curve_id INTEGER NOT NULL REFERENCES curves(id) ON DELETE CASCADE,
    name     TEXT NOT NULL,
    value    TEXT,
    PRIMARY KEY (curve_id, name)
);
CREATE TABLE IF NOT EXISTS points (
    id           INTEGER PRIMARY KEY,
    curve_id     INTEGER NOT NULL REFERENCES curves(id) ON DELETE CASCADE,
    t            REAL NOT NULL,          -- часы от старта (произв., для сортировки старых баз)
    ts_iso       TEXT,                   -- абсолютные дата+время точки (источник истины)
    recorded_iso TEXT
);
CREATE TABLE IF NOT EXISTS point_values (
    point_id INTEGER NOT NULL REFERENCES points(id) ON DELETE CASCADE,
    var      TEXT NOT NULL,
    value    REAL,
    PRIMARY KEY (point_id, var)
);
"""


@dataclass
class Property:
    name: str
    kind: str                  # 'enum' | 'numeric'
    options: list[str] | None  # ограничение для enum: список допустимых вариантов
    unit: str | None
    position: int
    min_val: float | None = None  # ограничение для numeric: нижняя граница
    max_val: float | None = None  # ограничение для numeric: верхняя граница


@dataclass
class MeasuredVar:
    name: str
    unit: str | None
    position: int


@dataclass
class Curve:
    id: int
    name: str
    start_iso: str
    finished: bool
    created_iso: str
    flags: int = 0  # битовая маска цветных флагов

    def flag_prefix(self) -> str:
        """Эмодзи выставленных флагов (для списка)."""
        return "".join(FLAG_LABELS[i] for i in range(FLAG_COUNT) if self.flags & (1 << i))


@dataclass
class Point:
    id: int
    t: float
    values: dict[str, float]
    recorded_iso: str | None
    ts_iso: str | None = None

    @property
    def ts(self) -> datetime | None:
        """Абсолютная дата+время точки (или None для очень старых баз)."""
        return datetime.fromisoformat(self.ts_iso) if self.ts_iso else None


def _safe_filename(name: str) -> str:
    """Имя файла из имени кривой (без небезопасных символов)."""
    safe = re.sub(r"[^\w.-]+", "_", name.strip(), flags=re.UNICODE).strip("_")
    return safe or "curve"


class RecordingDB:
    """Обёртка над SQLite-файлом одного эксперимента."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(_SCHEMA)
        self._migrate()
        self.conn.commit()
        if self.get_setting("time_unit") is None:
            self.set_setting("time_unit", "h")

    def _migrate(self) -> None:
        """Добавить недостающие колонки в старые базы."""
        pcols = {r["name"] for r in self.conn.execute("PRAGMA table_info(properties)")}
        for col in ("min_val", "max_val"):
            if col not in pcols:
                self.conn.execute(f"ALTER TABLE properties ADD COLUMN {col} REAL")

        ccols = {r["name"] for r in self.conn.execute("PRAGMA table_info(curves)")}
        if "flags" not in ccols:
            self.conn.execute("ALTER TABLE curves ADD COLUMN flags INTEGER NOT NULL DEFAULT 0")

        ptcols = {r["name"] for r in self.conn.execute("PRAGMA table_info(points)")}
        if "ts_iso" not in ptcols:
            self.conn.execute("ALTER TABLE points ADD COLUMN ts_iso TEXT")
            self._backfill_ts()

    def _backfill_ts(self) -> None:
        """Заполнить ts_iso старых точек: ts = start + t (elapsed в текущей единице)."""
        factor = _HOURS_TO_UNIT[str(self.get_setting("time_unit", "h")) or "h"]
        rows = self.conn.execute(
            "SELECT p.id AS pid, p.t AS t, c.start_iso AS start "
            "FROM points p JOIN curves c ON c.id = p.curve_id WHERE p.ts_iso IS NULL"
        ).fetchall()
        for r in rows:
            try:
                start = datetime.fromisoformat(r["start"])
                ts = start + timedelta(hours=r["t"] / factor)
                self.conn.execute("UPDATE points SET ts_iso=? WHERE id=?",
                                  (ts.isoformat(sep=" ", timespec="seconds"), r["pid"]))
            except (ValueError, TypeError, ZeroDivisionError):
                continue

    def is_empty_schema(self) -> bool:
        """Схема ещё не задана (нет ни свойств, ни измеряемых величин)."""
        return not self.list_properties() and not self.list_measured_vars()

    def close(self) -> None:
        self.conn.close()

    # ---------- настройки ----------
    def get_setting(self, key: str, default: object = None) -> object:
        row = self.conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: object) -> None:
        self.conn.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )
        self.conn.commit()

    @property
    def time_unit(self) -> str:
        u = str(self.get_setting("time_unit", "h"))
        return u if u in TIME_UNITS else "h"

    @time_unit.setter
    def time_unit(self, unit: str) -> None:
        if unit not in TIME_UNITS:
            raise ValueError(f"неизвестная единица времени: {unit}")
        self.set_setting("time_unit", unit)

    @property
    def time_column(self) -> str:
        return TIME_COLUMN[self.time_unit]

    # ---------- схема: свойства-условия ----------
    def list_properties(self) -> list[Property]:
        rows = self.conn.execute(
            "SELECT name,kind,options,unit,position,min_val,max_val "
            "FROM properties ORDER BY position"
        ).fetchall()
        return [
            Property(
                name=r["name"], kind=r["kind"],
                options=json.loads(r["options"]) if r["options"] else None,
                unit=r["unit"], position=r["position"],
                min_val=r["min_val"], max_val=r["max_val"],
            )
            for r in rows
        ]

    def replace_properties(self, props: list[Property]) -> None:
        """Полностью заменить список свойств (порядок = позиция)."""
        cur = self.conn
        cur.execute("DELETE FROM properties")
        for i, p in enumerate(props):
            cur.execute(
                "INSERT INTO properties(name,kind,options,unit,position,min_val,max_val) "
                "VALUES(?,?,?,?,?,?,?)",
                (p.name, p.kind, json.dumps(p.options) if p.options else None,
                 p.unit, i, p.min_val, p.max_val),
            )
        cur.commit()

    # ---------- схема: измеряемые величины ----------
    def list_measured_vars(self) -> list[MeasuredVar]:
        rows = self.conn.execute(
            "SELECT name,unit,position FROM measured_vars ORDER BY position"
        ).fetchall()
        return [MeasuredVar(name=r["name"], unit=r["unit"], position=r["position"]) for r in rows]

    def measured_names(self) -> list[str]:
        return [v.name for v in self.list_measured_vars()]

    def replace_measured_vars(self, vars_: list[MeasuredVar]) -> None:
        cur = self.conn
        cur.execute("DELETE FROM measured_vars")
        for i, v in enumerate(vars_):
            cur.execute(
                "INSERT INTO measured_vars(name,unit,position) VALUES(?,?,?)",
                (v.name, v.unit, i),
            )
        cur.commit()

    # ---------- кривые ----------
    def create_curve(self, name: str, meta: dict[str, object],
                     start_iso: str | None = None) -> int:
        now = datetime.now().replace(microsecond=0)
        start = start_iso or now.isoformat(sep=" ")
        cur = self.conn.execute(
            "INSERT INTO curves(name,start_iso,finished,created_iso) VALUES(?,?,0,?)",
            (name, start, now.isoformat(sep=" ")),
        )
        cid = int(cur.lastrowid)
        for k, v in meta.items():
            self.conn.execute(
                "INSERT INTO curve_meta(curve_id,name,value) VALUES(?,?,?)",
                (cid, str(k), None if v is None else str(v)),
            )
        self.conn.commit()
        return cid

    def _curve_from_row(self, r) -> Curve:
        return Curve(id=r["id"], name=r["name"], start_iso=r["start_iso"],
                     finished=bool(r["finished"]), created_iso=r["created_iso"],
                     flags=r["flags"])

    def list_curves(self) -> list[Curve]:
        rows = self.conn.execute(
            "SELECT id,name,start_iso,finished,created_iso,flags FROM curves ORDER BY id"
        ).fetchall()
        return [self._curve_from_row(r) for r in rows]

    def get_curve(self, curve_id: int) -> Curve:
        r = self.conn.execute(
            "SELECT id,name,start_iso,finished,created_iso,flags FROM curves WHERE id=?",
            (curve_id,),
        ).fetchone()
        if r is None:
            raise KeyError(f"нет кривой id={curve_id}")
        return self._curve_from_row(r)

    def get_curve_meta(self, curve_id: int) -> dict[str, str]:
        rows = self.conn.execute(
            "SELECT name,value FROM curve_meta WHERE curve_id=?", (curve_id,)
        ).fetchall()
        return {r["name"]: r["value"] for r in rows}

    def set_finished(self, curve_id: int, finished: bool = True) -> None:
        self.conn.execute("UPDATE curves SET finished=? WHERE id=?",
                          (1 if finished else 0, curve_id))
        self.conn.commit()

    def delete_curve(self, curve_id: int) -> None:
        self.conn.execute("DELETE FROM curves WHERE id=?", (curve_id,))
        self.conn.commit()

    # ---------- флаги ----------
    def get_flags(self, curve_id: int) -> int:
        r = self.conn.execute("SELECT flags FROM curves WHERE id=?", (curve_id,)).fetchone()
        return int(r["flags"]) if r else 0

    def toggle_flag(self, curve_id: int, index: int) -> None:
        """Переключить флаг index (0..FLAG_COUNT-1) у кривой."""
        flags = self.get_flags(curve_id) ^ (1 << index)
        self.conn.execute("UPDATE curves SET flags=? WHERE id=?", (flags, curve_id))
        self.conn.commit()

    # ---------- точки ----------
    def add_point(self, curve_id: int, ts: datetime, values: dict[str, float],
                  recorded_iso: str | None = None) -> int:
        """Добавить точку с абсолютным временем ts (дата+время).

        Часы-от-старта (t) вычисляются и сохраняются для совместимости/сортировки.
        """
        start = datetime.fromisoformat(self.get_curve(curve_id).start_iso)
        t_hours = (ts - start).total_seconds() / 3600.0
        cur = self.conn.execute(
            "INSERT INTO points(curve_id,t,ts_iso,recorded_iso) VALUES(?,?,?,?)",
            (curve_id, t_hours, ts.isoformat(sep=" ", timespec="seconds"), recorded_iso),
        )
        pid = int(cur.lastrowid)
        for var, val in values.items():
            if val is None or (isinstance(val, float) and np.isnan(val)):
                continue
            self.conn.execute(
                "INSERT INTO point_values(point_id,var,value) VALUES(?,?,?)",
                (pid, var, float(val)),
            )
        self.conn.commit()
        return pid

    def list_points(self, curve_id: int) -> list[Point]:
        prows = self.conn.execute(
            "SELECT id,t,ts_iso,recorded_iso FROM points WHERE curve_id=? "
            "ORDER BY ts_iso, t, id",
            (curve_id,),
        ).fetchall()
        points: list[Point] = []
        for r in prows:
            vals = {
                vr["var"]: vr["value"]
                for vr in self.conn.execute(
                    "SELECT var,value FROM point_values WHERE point_id=?", (r["id"],)
                ).fetchall()
            }
            points.append(Point(id=r["id"], t=r["t"], values=vals,
                                recorded_iso=r["recorded_iso"], ts_iso=r["ts_iso"]))
        return points

    def delete_point(self, point_id: int) -> None:
        self.conn.execute("DELETE FROM points WHERE id=?", (point_id,))
        self.conn.commit()

    def last_ts(self, curve_id: int) -> datetime | None:
        """Время последней (самой поздней) точки кривой."""
        r = self.conn.execute(
            "SELECT MAX(ts_iso) AS m FROM points WHERE curve_id=?", (curve_id,)
        ).fetchone()
        return datetime.fromisoformat(r["m"]) if r and r["m"] else None

    def last_time(self, curve_id: int) -> float | None:
        r = self.conn.execute(
            "SELECT MAX(t) AS m FROM points WHERE curve_id=?", (curve_id,)
        ).fetchone()
        return r["m"] if r and r["m"] is not None else None

    def elapsed_since_start(self, curve_id: int, when: datetime | None = None) -> float:
        """Прошедшее время от старта кривой в текущих единицах («сейчас»)."""
        curve = self.get_curve(curve_id)
        start = datetime.fromisoformat(curve.start_iso)
        when = when or datetime.now()
        hours = (when - start).total_seconds() / 3600.0
        return hours * _HOURS_TO_UNIT[self.time_unit]

    # ---------- экспорт ----------
    def build_meta(self, curve_id: int) -> dict[str, object]:
        curve = self.get_curve(curve_id)
        meta: dict[str, object] = {"sample_name": curve.name, "start_date": curve.start_iso}
        meta.update(self.get_curve_meta(curve_id))
        return meta

    def build_dataframe(self, curve_id: int) -> pd.DataFrame:
        """Лист data: 1-й столбец — абсолютная дата+время, дальше измеряемые.

        Столбец datetime пишется как настоящая Excel-дата (datetime64).
        """
        vars_ = self.measured_names()
        rows = []
        for p in self.list_points(curve_id):
            row: dict[str, object] = {DATETIME_COLUMN: p.ts}
            for v in vars_:
                row[v] = p.values.get(v, np.nan)
            rows.append(row)
        df = pd.DataFrame(rows, columns=[DATETIME_COLUMN, *vars_])
        df[DATETIME_COLUMN] = pd.to_datetime(df[DATETIME_COLUMN])
        return df

    def export_curve(self, curve_id: int, folder: str | Path,
                     filename: str | None = None) -> Path:
        curve = self.get_curve(curve_id)
        fname = filename or f"{_safe_filename(curve.name)}.xlsx"
        path = Path(folder) / fname
        write_sample(path, self.build_meta(curve_id), self.build_dataframe(curve_id))
        return path

    def export_curves(self, curve_ids: list[int], folder: str | Path,
                      skip_empty: bool = False) -> list[Path]:
        """Батч-экспорт выбранных кривых (с разведением одинаковых имён)."""
        folder = Path(folder)
        used: set[str] = set()
        paths: list[Path] = []
        for cid in curve_ids:
            if skip_empty and not self.list_points(cid):
                continue
            base = _safe_filename(self.get_curve(cid).name)
            fname = f"{base}.xlsx"
            if fname in used:                       # избегаем коллизий имён
                fname = f"{base}_{cid}.xlsx"
            used.add(fname)
            paths.append(self.export_curve(cid, folder, filename=fname))
        return paths

    def export_all(self, folder: str | Path, skip_empty: bool = False) -> list[Path]:
        ids = [c.id for c in self.list_curves()]
        return self.export_curves(ids, folder, skip_empty=skip_empty)
