"""EHX 下线防错程序 SQLite 数据层。"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA busy_timeout = 10000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS material_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_code TEXT NOT NULL UNIQUE,
                    material_name TEXT NOT NULL,
                    customer_material_code TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS offline_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    offline_order_no TEXT NOT NULL UNIQUE,
                    box_no TEXT NOT NULL UNIQUE,
                    material_code TEXT NOT NULL DEFAULT '',
                    material_name TEXT NOT NULL DEFAULT '',
                    customer_material_code TEXT NOT NULL DEFAULT '',
                    qty INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    pdf_path TEXT NOT NULL DEFAULT '',
                    printed INTEGER NOT NULL DEFAULT 0,
                    print_error TEXT NOT NULL DEFAULT '',
                    printed_at TEXT,
                    reprint_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS scan_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    offline_order_no TEXT NOT NULL,
                    box_no TEXT NOT NULL,
                    material_code TEXT NOT NULL DEFAULT '',
                    material_name TEXT NOT NULL DEFAULT '',
                    customer_material_code TEXT NOT NULL DEFAULT '',
                    barcode TEXT NOT NULL,
                    scan_index INTEGER NOT NULL,
                    scan_time TEXT NOT NULL,
                    result TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '',
                    printed INTEGER NOT NULL DEFAULT 0,
                    computer_name TEXT NOT NULL DEFAULT '',
                    line_name TEXT NOT NULL DEFAULT '',
                    station_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (offline_order_no)
                        REFERENCES offline_orders(offline_order_no)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                    uq_scan_records_success_barcode
                    ON scan_records(barcode)
                    WHERE result = '成功';
                CREATE INDEX IF NOT EXISTS idx_scan_records_barcode
                    ON scan_records(barcode);
                CREATE INDEX IF NOT EXISTS idx_scan_records_order
                    ON scan_records(offline_order_no, id);
                CREATE INDEX IF NOT EXISTS idx_scan_records_time
                    ON scan_records(scan_time);
                CREATE INDEX IF NOT EXISTS idx_orders_created
                    ON offline_orders(created_at);
                """
            )

    def upsert_materials(self, materials: Iterable[Any]) -> int:
        now = _now()
        rows = []
        for item in materials:
            data = asdict(item) if is_dataclass(item) else dict(item)
            rows.append(
                (
                    str(data["material_code"]).strip(),
                    str(data["material_name"]).strip(),
                    str(data["customer_material_code"]).strip(),
                    now,
                    now,
                )
            )
        with self.connect() as connection:
            connection.executemany(
                """
                INSERT INTO material_mapping (
                    material_code, material_name, customer_material_code,
                    enabled, created_at, updated_at
                ) VALUES (?, ?, ?, 1, ?, ?)
                ON CONFLICT(material_code) DO UPDATE SET
                    material_name = excluded.material_name,
                    customer_material_code = excluded.customer_material_code,
                    enabled = 1,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
        return len(rows)

    def get_enabled_materials(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT material_code, material_name, customer_material_code
                FROM material_mapping
                WHERE enabled = 1
                ORDER BY length(material_code) DESC, material_code
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def create_order(
        self, offline_order_no: str, box_no: str, target_qty: int
    ) -> dict[str, Any]:
        now = _now()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO offline_orders (
                    offline_order_no, box_no, qty, status, created_at, updated_at
                ) VALUES (?, ?, ?, 'SCANNING', ?, ?)
                """,
                (offline_order_no, box_no, target_qty, now, now),
            )
        return self.get_order(offline_order_no)

    def get_order(self, offline_order_no: str) -> dict[str, Any]:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM offline_orders WHERE offline_order_no = ?",
                (offline_order_no,),
            ).fetchone()
        if row is None:
            raise KeyError(f"下线单不存在：{offline_order_no}")
        return dict(row)

    def get_recoverable_order(self) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM offline_orders
                WHERE status IN (
                    'SCANNING', 'PDF_GENERATING', 'PDF_FAILED',
                    'READY_TO_PRINT', 'PRINT_FAILED'
                )
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def set_order_material(
        self,
        offline_order_no: str,
        material_code: str,
        material_name: str,
        customer_material_code: str,
    ) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE offline_orders SET
                    material_code = ?,
                    material_name = ?,
                    customer_material_code = ?,
                    updated_at = ?
                WHERE offline_order_no = ?
                """,
                (
                    material_code,
                    material_name,
                    customer_material_code,
                    _now(),
                    offline_order_no,
                ),
            )

    def accepted_barcode_exists(self, barcode: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM scan_records
                WHERE barcode = ? AND result = '成功'
                LIMIT 1
                """,
                (barcode,),
            ).fetchone()
        return row is not None

    def accepted_count(self, offline_order_no: str) -> int:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT count(*) FROM scan_records
                WHERE offline_order_no = ? AND result = '成功'
                """,
                (offline_order_no,),
            ).fetchone()
        return int(row[0])

    def record_scan(
        self,
        *,
        offline_order_no: str,
        box_no: str,
        barcode: str,
        scan_index: int,
        result: str,
        message: str,
        material_code: str = "",
        material_name: str = "",
        customer_material_code: str = "",
        computer_name: str = "",
        line_name: str = "",
        station_name: str = "",
    ) -> int:
        now = _now()
        with self.connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scan_records (
                    offline_order_no, box_no,
                    material_code, material_name, customer_material_code,
                    barcode, scan_index, scan_time, result, message, printed,
                    computer_name, line_name, station_name, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)
                """,
                (
                    offline_order_no,
                    box_no,
                    material_code,
                    material_name,
                    customer_material_code,
                    barcode,
                    scan_index,
                    now,
                    result,
                    message,
                    computer_name,
                    line_name,
                    station_name,
                    now,
                ),
            )
            return int(cursor.lastrowid)

    def successful_scans(self, offline_order_no: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM scan_records
                WHERE offline_order_no = ? AND result = '成功'
                ORDER BY scan_index, id
                """,
                (offline_order_no,),
            ).fetchall()
        return [dict(row) for row in rows]

    def update_order_status(
        self,
        offline_order_no: str,
        status: str,
        *,
        pdf_path: str | None = None,
        print_error: str | None = None,
    ) -> None:
        fields = ["status = ?", "updated_at = ?"]
        parameters: list[Any] = [status, _now()]
        if pdf_path is not None:
            fields.append("pdf_path = ?")
            parameters.append(pdf_path)
        if print_error is not None:
            fields.append("print_error = ?")
            parameters.append(print_error)
        parameters.append(offline_order_no)
        with self.connect() as connection:
            connection.execute(
                f"""
                UPDATE offline_orders
                SET {", ".join(fields)}
                WHERE offline_order_no = ?
                """,
                parameters,
            )

    def mark_printed(self, offline_order_no: str, *, reprint: bool = False) -> None:
        now = _now()
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE offline_orders SET
                    status = 'PRINTED',
                    printed = 1,
                    print_error = '',
                    printed_at = ?,
                    reprint_count = reprint_count + ?,
                    updated_at = ?
                WHERE offline_order_no = ?
                """,
                (now, 1 if reprint else 0, now, offline_order_no),
            )
            connection.execute(
                """
                UPDATE scan_records SET printed = 1
                WHERE offline_order_no = ? AND result = '成功'
                """,
                (offline_order_no,),
            )

    def history_by_barcode(self, barcode: str) -> list[dict[str, Any]]:
        return self._query_records(
            "WHERE r.barcode = ? ORDER BY r.id DESC", (barcode,)
        )

    def history_by_order(self, offline_order_no: str) -> list[dict[str, Any]]:
        return self._query_records(
            "WHERE r.offline_order_no = ? ORDER BY r.id", (offline_order_no,)
        )

    def history_by_date(self, value: date | str) -> list[dict[str, Any]]:
        date_text = value.isoformat() if isinstance(value, date) else str(value)
        return self._query_records(
            "WHERE substr(r.scan_time, 1, 10) = ? ORDER BY r.id DESC",
            (date_text,),
        )

    def recent_records(self, limit: int = 10) -> list[dict[str, Any]]:
        return self._query_records(
            "ORDER BY r.id DESC LIMIT ?", (max(1, int(limit)),)
        )

    def _query_records(
        self, clause: str, parameters: tuple[Any, ...]
    ) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    r.*,
                    o.status AS order_status,
                    o.pdf_path,
                    o.printed_at,
                    o.reprint_count
                FROM scan_records r
                JOIN offline_orders o
                  ON o.offline_order_no = r.offline_order_no
                {clause}
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
