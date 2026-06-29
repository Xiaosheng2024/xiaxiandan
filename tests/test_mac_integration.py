from __future__ import annotations

import platform
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader

from ehx_guard.config import RuntimeConfig
from ehx_guard.database import Database
from ehx_guard.materials import Material, MaterialRepository
from ehx_guard.scanner_service import ScannerService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(platform.system() == "Darwin", "仅验证 macOS 调试模式")
class MacIntegrationTest(unittest.TestCase):
    def test_full_box_generates_pdf_images_and_skips_print(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            root = Path(temp_dir_text)
            database = Database(root / "data/ehx.db")
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
                box_scan_count=1,
                template_path=str(
                    PROJECT_ROOT
                    / "Wologic/System/报交下线单模板.xlsx"
                ),
                output_pdf_dir=str(root / "output/pdf"),
                barcode_output_dir=str(root / "output/barcodes"),
                database_path=str(root / "data/ehx.db"),
                material_excel_path=str(root / "unused.xlsx"),
                barcode_mode="image",
                barcode_show_text=True,
                debug_no_print_on_mac=True,
                mac_pdf_renderer="reportlab",
                reserved1_sub="2918",
            )
            service = ScannerService(
                config,
                database,
                MaterialRepository(database, root / "unused.xlsx"),
            )
            order_no = service.state.offline_order_no
            outcome = service.process_barcode(
                "5664620-CLBK0620260616001"
            )

            order = database.get_order(order_no)
            pdf_path = Path(order["pdf_path"])
            reader = PdfReader(str(pdf_path))
            text = reader.pages[0].extract_text()

            self.assertEqual("PDF已生成", outcome.result)
            self.assertEqual("PDF_ONLY", order["status"])
            self.assertEqual(0, order["printed"])
            self.assertTrue(pdf_path.is_file())
            self.assertTrue(pdf_path.with_suffix(".xlsx").is_file())
            self.assertEqual(1, len(reader.pages))
            self.assertGreaterEqual(len(reader.pages[0].images), 4)
            self.assertIn("5664620-CLBK06", text)
            self.assertIn("566462001FA2", text)
            self.assertIn("2918", text)
            self.assertIn(order_no, text)
            self.assertEqual(
                4, len(list((root / "output/barcodes").glob("*.png")))
            )
            history = database.history_by_order(order_no)
            self.assertEqual(1, len(history))
            self.assertEqual("成功", history[0]["result"])


if __name__ == "__main__":
    unittest.main()
