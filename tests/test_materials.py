from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ehx_guard.database import Database
from ehx_guard.materials import MaterialRepository


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class MaterialRepositoryTest(unittest.TestCase):
    def test_import_current_excel_and_identify_sample_barcode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Database(Path(temp_dir) / "materials.db")
            repository = MaterialRepository(
                database, PROJECT_ROOT / "EHX物料号匹配.xlsx"
            )
            count = repository.import_excel()
            materials = repository.load()
            matched = repository.identify(
                "5664620-CLBK0620260616001"
            )

            self.assertGreaterEqual(count, 6)
            self.assertEqual(count, len(materials))
            self.assertIsNotNone(matched)
            self.assertEqual("5664620-CLBK06", matched.material_code)
            self.assertEqual("566462001FA2", matched.customer_material_code)


if __name__ == "__main__":
    unittest.main()
