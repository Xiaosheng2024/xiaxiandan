from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

from ehx_guard.config import RuntimeConfig
from ehx_guard.database import Database
from ehx_guard.materials import MaterialRepository
from ehx_guard.scanner_service import ScannerService


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _UnusedDependency:
    pass


class _NoNetworkMii:
    def upload_offline_order(self, data):
        return False


def _write_material_excel(path: Path, rows: list[list[object]]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(
        ["物料条码前缀", "物料名称", "客户物料号/SAP物料号", "每箱数量"]
    )
    for row in rows:
        worksheet.append(row)
    workbook.save(path)
    workbook.close()


class MaterialRepositoryTest(unittest.TestCase):
    def test_import_current_excel_and_identify_sample_barcode(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Database(
                Path(temp_dir) / "materials.db",
                default_box_scan_count=6,
            )
            repository = MaterialRepository(
                database,
                PROJECT_ROOT / "EHX物料号匹配.xlsx",
                default_box_scan_count=6,
            )
            result = repository.import_excel()
            materials = repository.load()
            matched = repository.identify(
                "5664620-CLBK0620260616001"
            )

            self.assertGreaterEqual(result.added, 6)
            self.assertEqual(result.added, len(materials))
            self.assertIsNotNone(matched)
            self.assertEqual("5664620-CLBK06", matched.material_code)
            self.assertEqual("566462001FA2", matched.customer_material_code)
            self.assertEqual(44, matched.box_scan_count)

            service = ScannerService(
                RuntimeConfig(
                    box_scan_count=6,
                    output_pdf_dir=str(Path(temp_dir) / "pdf"),
                    database_path=str(Path(temp_dir) / "materials.db"),
                    material_excel_path=str(
                        PROJECT_ROOT / "EHX物料号匹配.xlsx"
                    ),
                ),
                database,
                repository,
                pdf_generator=_UnusedDependency(),
                printer=_UnusedDependency(),
                mii_client=_NoNetworkMii(),
            )
            outcome = service.process_barcode(
                "5664620-CLBK0620260616001"
            )
            self.assertEqual(44, outcome.state.required_count)

    def test_blank_box_count_uses_config_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            root = Path(temp_dir_text)
            excel_path = root / "materials.xlsx"
            _write_material_excel(
                excel_path,
                [["MAT-A", "物料A", "SAP-A", None]],
            )
            database = Database(
                root / "data.db", default_box_scan_count=10
            )
            repository = MaterialRepository(
                database,
                excel_path,
                default_box_scan_count=10,
            )
            repository.import_excel()
            self.assertEqual(10, repository.load()[0].box_scan_count)

    def test_non_numeric_box_count_reports_exact_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            root = Path(temp_dir_text)
            excel_path = root / "materials.xlsx"
            _write_material_excel(
                excel_path,
                [["MAT-A", "物料A", "SAP-A", "不是数字"]],
            )
            repository = MaterialRepository(
                Database(root / "data.db"),
                excel_path,
                default_box_scan_count=6,
            )
            with self.assertRaisesRegex(
                ValueError, "第 2 行每箱数量不是数字"
            ):
                repository.import_excel()

    def test_reimport_reports_add_update_and_disable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            root = Path(temp_dir_text)
            excel_path = root / "materials.xlsx"
            database = Database(root / "data.db")
            repository = MaterialRepository(database, excel_path)
            _write_material_excel(
                excel_path,
                [
                    ["MAT-A", "物料A", "SAP-A", 6],
                    ["MAT-B", "物料B", "SAP-B", 10],
                ],
            )
            first = repository.import_excel()
            self.assertEqual((2, 0, 0), (first.added, first.updated, first.disabled))

            _write_material_excel(
                excel_path,
                [
                    ["MAT-A", "物料A已更新", "SAP-A", 12],
                    ["MAT-C", "物料C", "SAP-C", 20],
                ],
            )
            second = repository.import_excel()
            self.assertEqual(
                (1, 1, 1),
                (second.added, second.updated, second.disabled),
            )
            self.assertEqual(
                {"MAT-A", "MAT-C"},
                {item.material_code for item in repository.reload()},
            )

    def test_restart_style_refresh_applies_excel_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir_text:
            root = Path(temp_dir_text)
            excel_path = root / "materials.xlsx"
            database = Database(root / "data.db")
            repository = MaterialRepository(database, excel_path)
            _write_material_excel(
                excel_path,
                [["MAT-A", "物料A", "SAP-A", 6]],
            )
            repository.load(refresh_from_excel=True)
            self.assertEqual(6, repository.reload()[0].box_scan_count)

            _write_material_excel(
                excel_path,
                [["MAT-A", "物料A", "SAP-A", 12]],
            )
            repository.load(refresh_from_excel=True)
            self.assertEqual(12, repository.reload()[0].box_scan_count)


if __name__ == "__main__":
    unittest.main()
