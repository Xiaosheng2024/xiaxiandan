from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ehx_guard.config import load_config
from ehx_guard.printing import SumatraPdfPrinter


class ConfigAndPrintingTest(unittest.TestCase):
    def test_config_defaults_disable_office_pdf_on_mac(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config = load_config(Path(temp_dir) / "missing.json")
        self.assertFalse(config.enable_office_pdf_on_mac)
        self.assertEqual("2918", config.reserved1_sub)
        self.assertEqual("image", config.barcode_mode)
        self.assertTrue(config.barcode_show_text)
        self.assertEqual("excel_com", config.pdf_renderer)
        self.assertEqual("excel_com", config.print_method)
        self.assertTrue(config.debug_no_print_on_mac)
        self.assertEqual("reportlab", config.mac_pdf_renderer)
        self.assertEqual("excel_com", config.windows_pdf_renderer)
        self.assertEqual("excel_com", config.windows_print_method)

    def test_non_windows_print_failure_preserves_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            pdf_path = Path(temp_dir_text) / "order.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n%%EOF\n")
            printer = SumatraPdfPrinter(printer_name="Test Printer")
            with patch("ehx_guard.printing.os.name", "posix"):
                result = printer.print_pdf(pdf_path)
            self.assertFalse(result.success)
            self.assertTrue(pdf_path.is_file())
            self.assertIn("仅支持 Windows", result.message)

    def test_missing_pdf_returns_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.pdf"
            result = SumatraPdfPrinter().print_pdf(missing)
            self.assertFalse(result.success)
            self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
