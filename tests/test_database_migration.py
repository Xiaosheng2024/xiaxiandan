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


if __name__ == "__main__":
    unittest.main()
