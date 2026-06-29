from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ehx_guard.config import RuntimeConfig
from ehx_guard.database import Database
from ehx_guard.gui import MainWindow
from ehx_guard.materials import Material, MaterialRepository
from ehx_guard.scanner_service import ScannerService


class _UnusedDependency:
    pass


class _NoNetworkMii:
    def upload_offline_order(self, data):
        return False


class GuiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_window_opens_and_accepts_scanner_enter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            temp_dir = Path(temp_dir_text)
            database = Database(temp_dir / "gui.db")
            database.upsert_materials(
                [
                    Material(
                        "5664620-CLBK06",
                        "主驾座椅背板总成 极夜黑",
                        "566462001FA2",
                    )
                ]
            )
            config = RuntimeConfig(
                box_scan_count=6,
                database_path=str(temp_dir / "gui.db"),
                output_pdf_dir=str(temp_dir / "pdf"),
                material_excel_path=str(temp_dir / "unused.xlsx"),
            )
            service = ScannerService(
                config,
                database,
                MaterialRepository(database, temp_dir / "unused.xlsx"),
                pdf_generator=_UnusedDependency(),
                printer=_UnusedDependency(),
                mii_client=_NoNetworkMii(),
            )
            window = MainWindow(service)
            window.show()
            self.application.processEvents()
            window.scan_input.setText("5664620-CLBK0620260616001")
            window.scan_input.returnPressed.emit()
            self.application.processEvents()

            self.assertTrue(window.isVisible())
            self.assertEqual(1, service.state.scanned_count)
            self.assertGreaterEqual(window.recent_table.rowCount(), 1)
            window.close()


if __name__ == "__main__":
    unittest.main()
