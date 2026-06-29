from __future__ import annotations

import unittest

from scripts.check_runtime import _configured_printer_check


class RuntimePrinterCheckTest(unittest.TestCase):
    def test_empty_name_uses_default_printer(self) -> None:
        self.assertIn("默认打印机", _configured_printer_check("", None))

    def test_existing_configured_printer_is_confirmed(self) -> None:
        message = _configured_printer_check("HP LaserJet", True)
        self.assertIn("已找到", message)
        self.assertIn("HP LaserJet", message)

    def test_missing_configured_printer_has_actionable_message(self) -> None:
        message = _configured_printer_check("Missing Printer", False)
        self.assertIn("未找到", message)
        self.assertIn("config.json", message)
        self.assertIn("Get-Printer", message)


if __name__ == "__main__":
    unittest.main()
