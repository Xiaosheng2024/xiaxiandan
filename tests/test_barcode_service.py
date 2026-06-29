from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from ehx_guard.barcode_service import generate_code128_png


class BarcodeServiceTest(unittest.TestCase):
    def test_generate_code128_png_with_and_without_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            temp_dir = Path(temp_dir_text)
            with_text = generate_code128_png(
                "566462001FA2",
                temp_dir / "with_text.png",
                show_text=True,
            )
            without_text = generate_code128_png(
                "EHX20260629185500",
                temp_dir / "without_text.png",
                show_text=False,
            )

            with Image.open(with_text) as first, Image.open(without_text) as second:
                self.assertEqual("PNG", first.format)
                self.assertEqual("PNG", second.format)
                self.assertGreater(first.width, 300)
                self.assertGreater(second.width, 300)
                self.assertGreater(first.height, second.height)
                self.assertIn(0, first.convert("L").getextrema())
                self.assertIn(255, first.convert("L").getextrema())

    def test_empty_value_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(ValueError):
                generate_code128_png("", Path(temp_dir) / "empty.png")


if __name__ == "__main__":
    unittest.main()
