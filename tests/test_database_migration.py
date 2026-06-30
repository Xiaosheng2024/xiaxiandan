from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from ehx_guard.database import Database


class DatabaseMigrationTest(unittest.TestCase):
    def test_old_database_adds_box_and_required_count_columns(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "old.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE material_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_code TEXT NOT NULL UNIQUE,
                    material_name TEXT NOT NULL,
                    customer_material_code TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO material_mapping (
                    material_code, material_name, customer_material_code,
                    enabled, created_at, updated_at
                ) VALUES ('MAT-A', '物料A', 'SAP-A', 1, 'now', 'now');

                CREATE TABLE offline_orders (
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
                INSERT INTO offline_orders (
                    offline_order_no, box_no, qty, status,
                    created_at, updated_at
                ) VALUES ('ORDER-1', 'BOX-1', 10, 'PRINTED', 'now', 'now');

                CREATE TABLE scan_records (
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
                    created_at TEXT NOT NULL
                );
                INSERT INTO scan_records (
                    offline_order_no, box_no, barcode, scan_index,
                    scan_time, result, created_at
                ) VALUES (
                    'ORDER-1', 'BOX-1', 'OLD-BARCODE', 1,
                    'now', '成功', 'now'
                );
                """
            )
            connection.commit()
            connection.close()

            database = Database(path, default_box_scan_count=44)
            materials = database.get_enabled_materials()
            order = database.get_order("ORDER-1")

            self.assertEqual(44, materials[0]["box_scan_count"])
            self.assertEqual(10, order["required_count"])
            self.assertEqual(10, order["qty"])
            with database.connect() as connection:
                scan_columns = {
                    row["name"]
                    for row in connection.execute(
                        "PRAGMA table_info(scan_records)"
                    ).fetchall()
                }
                index_sql = connection.execute(
                    """
                    SELECT sql FROM sqlite_master
                    WHERE type = 'index'
                      AND name = 'uq_scan_records_success_barcode'
                    """
                ).fetchone()["sql"]
            self.assertTrue(
                {"is_voided", "void_reason", "voided_at"} <= scan_columns
            )
            self.assertIn("is_voided = 0", index_sql)


if __name__ == "__main__":
    unittest.main()
