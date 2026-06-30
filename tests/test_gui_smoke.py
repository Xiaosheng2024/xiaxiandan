from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest

from ehx_guard.config import RuntimeConfig
from ehx_guard.database import Database
from ehx_guard.gui import HistoryDialog, MainWindow, MaterialDialog
from ehx_guard.materials import Material, MaterialRepository
from ehx_guard.printing import PrintResult
from ehx_guard.scanner_service import ScannerService


class _UnusedDependency:
    pass


class _NoNetworkMii:
    def upload_offline_order(self, data):
        return False


class _FakePdf:
    def generate(self, label, output_path):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\n%%EOF\n")
        return path


class _FakePrinter:
    def print_pdf(self, path):
        return PrintResult(
            success=True,
            pdf_path=Path(path),
            printer_name="Fake",
            message="ok",
        )


class GuiSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_window_opens_and_accepts_scanner_enter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            temp_dir = Path(temp_dir_text)
            database = Database(
                temp_dir / "gui.db", default_box_scan_count=6
            )
            database.upsert_materials(
                [
                    Material(
                        "5664620-CLBK06",
                        "主驾座椅背板总成 极夜黑",
                        "566462001FA2",
                        6,
                    ),
                    Material(
                        "5664618-CLBK06",
                        "副驾座椅背板总成 极夜黑",
                        "566461801FA2",
                        6,
                    ),
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
                MaterialRepository(
                    database,
                    temp_dir / "unused.xlsx",
                    default_box_scan_count=6,
                ),
                pdf_generator=_UnusedDependency(),
                printer=_UnusedDependency(),
                mii_client=_NoNetworkMii(),
            )
            window = MainWindow(service)
            window.show()
            self.application.processEvents()
            self.assertEqual("0/--", window.progress_big_label.text())
            self.assertEqual(
                -1, window.title_row.indexOf(window.progress_big_label)
            )
            self.assertGreaterEqual(
                window.progress_row.indexOf(window.progress_big_label), 0
            )
            self.assertEqual("重置当前箱", window.reset_button.text())

            window.scan_input.setText("5664620-CLBK0620260616001")
            window.scan_input.returnPressed.emit()
            self.application.processEvents()

            self.assertTrue(window.isVisible())
            self.assertEqual(1, service.state.scanned_count)
            self.assertEqual("1/6", window.progress_big_label.text())
            self.assertGreaterEqual(window.recent_table.rowCount(), 1)

            material_dialog = MaterialDialog(service, window)
            self.assertEqual(4, material_dialog.table.columnCount())
            self.assertEqual(
                "每箱数量",
                material_dialog.table.horizontalHeaderItem(3).text(),
            )
            self.assertEqual("6", material_dialog.table.item(0, 3).text())
            material_dialog.close()

            # 重复、混料、未配置均弹窗，且失败扫码不增加进度。
            window.scan_input.setText("5664620-CLBK0620260616001")
            window.scan_input.returnPressed.emit()
            self.application.processEvents()
            self.assertTrue(window.error_dialog.isVisible())
            self.assertEqual("重复", window.error_dialog.text())
            self.assertTrue(window.error_close_timer.isActive())
            self.assertEqual(3000, window.error_close_timer.interval())
            self.assertEqual("1/6", window.progress_big_label.text())

            window.scan_input.setText("5664618-CLBK0620260616001")
            window.scan_input.returnPressed.emit()
            self.application.processEvents()
            self.assertEqual("物料不一致", window.error_dialog.text())
            self.assertEqual("1/6", window.progress_big_label.text())

            window.scan_input.setText("9999999-UNKNOWN20260616001")
            window.scan_input.returnPressed.emit()
            self.application.processEvents()
            self.assertEqual("未配置物料", window.error_dialog.text())
            self.assertEqual("1/6", window.progress_big_label.text())

            QTest.qWait(3100)
            self.application.processEvents()
            self.assertFalse(
                window.error_dialog.isVisible(),
                (
                    f"timer_active={window.error_close_timer.isActive()} "
                    f"remaining={window.error_close_timer.remainingTime()}"
                ),
            )
            self.assertTrue(window.scan_input.hasFocus())

            window.focus_timer.stop()
            window.close()

    def test_reset_updates_progress_and_history_shows_voided_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            temp_dir = Path(temp_dir_text)
            database = Database(
                temp_dir / "reset.db", default_box_scan_count=44
            )
            database.upsert_materials(
                [
                    Material(
                        "5664620-CLBK06",
                        "主驾座椅背板总成 极夜黑",
                        "566462001FA2",
                        44,
                    )
                ]
            )
            config = RuntimeConfig(
                box_scan_count=44,
                database_path=str(temp_dir / "reset.db"),
                output_pdf_dir=str(temp_dir / "pdf"),
                material_excel_path=str(temp_dir / "unused.xlsx"),
            )
            service = ScannerService(
                config,
                database,
                MaterialRepository(
                    database,
                    temp_dir / "unused.xlsx",
                    default_box_scan_count=44,
                ),
                pdf_generator=_UnusedDependency(),
                printer=_UnusedDependency(),
                mii_client=_NoNetworkMii(),
            )
            window = MainWindow(service)
            window.show()
            for suffix in ("001", "002", "003"):
                window.scan_input.setText(
                    f"5664620-CLBK0620260616{suffix}"
                )
                window.scan_input.returnPressed.emit()
            self.application.processEvents()
            self.assertEqual("3/44", window.progress_big_label.text())
            old_order_no = service.state.offline_order_no

            def confirm_reset() -> None:
                dialog = QApplication.activeModalWidget()
                self.assertIsInstance(dialog, QMessageBox)
                for button in dialog.buttons():
                    if button.text() == "确认重置":
                        button.click()
                        return
                self.fail("未找到“确认重置”按钮")

            QTimer.singleShot(0, confirm_reset)
            window.reset_button.click()
            self.application.processEvents()
            self.assertEqual("0/44", window.progress_big_label.text())
            self.assertEqual("已作废", window.recent_table.item(0, 3).text())

            history = HistoryDialog(service, window)
            rows = database.history_by_order(old_order_no)
            history._populate(rows)
            self.assertEqual(12, history.table.columnCount())
            self.assertEqual(
                "已作废/重置", history.table.item(0, 8).text()
            )
            self.assertEqual("manual reset", history.table.item(0, 9).text())
            self.assertTrue(history.table.item(0, 10).text())
            history.close()

            # 作废条码可重扫；正常进度继续实时更新。
            window.scan_input.setText("5664620-CLBK0620260616001")
            window.scan_input.returnPressed.emit()
            self.application.processEvents()
            self.assertEqual("1/44", window.progress_big_label.text())

            window.focus_timer.stop()
            window.close()

    def test_full_box_briefly_shows_complete_then_new_box(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            temp_dir = Path(temp_dir_text)
            database = Database(
                temp_dir / "full.db", default_box_scan_count=44
            )
            database.upsert_materials(
                [
                    Material(
                        "5664620-CLBK06",
                        "主驾座椅背板总成 极夜黑",
                        "566462001FA2",
                        1,
                    )
                ]
            )
            config = RuntimeConfig(
                box_scan_count=44,
                database_path=str(temp_dir / "full.db"),
                output_pdf_dir=str(temp_dir / "pdf"),
                material_excel_path=str(temp_dir / "unused.xlsx"),
            )
            service = ScannerService(
                config,
                database,
                MaterialRepository(
                    database,
                    temp_dir / "unused.xlsx",
                    default_box_scan_count=44,
                ),
                pdf_generator=_FakePdf(),
                printer=_FakePrinter(),
                mii_client=_NoNetworkMii(),
            )
            window = MainWindow(service)
            window.show()
            window.scan_input.setText("5664620-CLBK0620260616001")
            window.scan_input.returnPressed.emit()
            self.application.processEvents()

            self.assertEqual("1/1", window.progress_big_label.text())
            QTest.qWait(900)
            self.application.processEvents()
            self.assertEqual("0/--", window.progress_big_label.text())

            window.focus_timer.stop()
            window.close()


if __name__ == "__main__":
    unittest.main()
