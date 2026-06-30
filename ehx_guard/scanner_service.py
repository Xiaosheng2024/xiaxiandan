"""扫码防错、满箱、PDF 和打印业务流程。"""

from __future__ import annotations

import logging
import platform
import socket
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import RuntimeConfig
from .database import Database
from .materials import Material, MaterialRepository
from .mii_client import MiiClient
from .pdf_generator import A5PdfGenerator, OfflineOrderLabel
from .printing import (
    DebugNoPrintPrinter,
    ExcelComPrinter,
    PrintResult,
)


@dataclass(frozen=True)
class BoxState:
    offline_order_no: str
    box_no: str
    material_code: str
    material_name: str
    customer_material_code: str
    required_count: int
    scanned_count: int
    remaining_count: int
    status: str


@dataclass(frozen=True)
class ScanOutcome:
    accepted: bool
    result: str
    message: str
    barcode: str
    state: BoxState
    box_completed: bool = False
    printed: bool = False


class ScannerService:
    def __init__(
        self,
        config: RuntimeConfig,
        database: Database,
        materials: MaterialRepository,
        *,
        pdf_generator: A5PdfGenerator | Any | None = None,
        printer: ExcelComPrinter | Any | None = None,
        mii_client: MiiClient | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.database = database
        self.materials = materials
        # 每次程序启动同步一次 Excel；运行中可通过物料窗口手动重新导入。
        self.materials.load(refresh_from_excel=True)
        self.logger = logger or logging.getLogger("ehx_guard.scanner")
        self.computer_name = socket.gethostname()
        system_name = platform.system()
        if system_name == "Darwin":
            pdf_renderer = config.mac_pdf_renderer
        elif system_name == "Windows":
            pdf_renderer = config.windows_pdf_renderer
        else:
            pdf_renderer = "reportlab"
        self.pdf_generator = pdf_generator or A5PdfGenerator(
            config.template_path,
            enable_libreoffice=False,
            barcode_mode=config.barcode_mode,
            barcode_show_text=config.barcode_show_text,
            barcode_output_dir=config.barcode_output_dir,
            pdf_renderer=pdf_renderer,
        )
        if printer is not None:
            self.printer = printer
        elif system_name == "Darwin" and config.debug_no_print_on_mac:
            self.printer = DebugNoPrintPrinter(
                logger=getattr(self.pdf_generator, "logger", self.logger)
            )
        elif system_name == "Windows":
            self.printer = ExcelComPrinter(
                printer_name=config.printer_name,
                logger=getattr(self.pdf_generator, "logger", self.logger),
            )
        else:
            self.printer = DebugNoPrintPrinter(
                logger=getattr(self.pdf_generator, "logger", self.logger),
            )
        self.mii_client = mii_client or MiiClient(
            enabled=config.mii_enabled,
            base_url=config.mii_base_url,
            token=config.mii_token,
            logger=self.logger,
        )
        self._order = self.database.get_recoverable_order()
        if self._order is None:
            self._order = self._create_next_order()

    @property
    def state(self) -> BoxState:
        self._order = self.database.get_order(self._order["offline_order_no"])
        scanned = self.database.accepted_count(self._order["offline_order_no"])
        required = int(self._order["required_count"])
        return BoxState(
            offline_order_no=self._order["offline_order_no"],
            box_no=self._order["box_no"],
            material_code=self._order["material_code"],
            material_name=self._order["material_name"],
            customer_material_code=self._order["customer_material_code"],
            required_count=required,
            scanned_count=scanned,
            remaining_count=max(0, required - scanned),
            status=self._order["status"],
        )

    def process_barcode(self, raw_barcode: str) -> ScanOutcome:
        barcode = (raw_barcode or "").strip()
        current = self.state
        if current.status != "SCANNING":
            return ScanOutcome(
                False,
                "待处理",
                "当前箱已满或存在生成/打印失败，请先重试处理",
                barcode,
                current,
            )

        next_index = current.scanned_count + 1
        if not barcode:
            return self._reject("", next_index, "格式错误", "条码不能为空")

        material = self.materials.identify(barcode)
        if material is None:
            return self._reject(
                barcode, next_index, "未配置物料", "条码前缀不在物料配置表中"
            )

        valid, format_message = self.materials.validate_full_barcode(
            barcode, material
        )
        if not valid:
            return self._reject(
                barcode,
                next_index,
                "格式错误",
                format_message,
                material=material,
            )

        if self.database.accepted_barcode_exists(barcode):
            return self._reject(
                barcode,
                next_index,
                "重复",
                "该完整条码已经成功扫描",
                material=material,
            )

        if current.material_code and material.material_code != current.material_code:
            return self._reject(
                barcode,
                next_index,
                "物料不一致",
                f"当前箱物料为 {current.material_code}",
                material=material,
            )

        if not current.material_code:
            required_count = (
                material.box_scan_count or self.config.box_scan_count
            )
            self.database.set_order_material(
                current.offline_order_no,
                material.material_code,
                material.material_name,
                material.customer_material_code,
                required_count,
            )

        try:
            self._record(
                barcode=barcode,
                scan_index=next_index,
                result="成功",
                message="扫码成功",
                material=material,
            )
        except sqlite3.IntegrityError:
            return self._reject(
                barcode,
                next_index,
                "重复",
                "该完整条码已经成功扫描",
                material=material,
            )

        updated = self.state
        if updated.scanned_count < updated.required_count:
            return ScanOutcome(
                True, "成功", "扫码成功", barcode, updated
            )
        return self._finalize_current_box(barcode)

    def retry_current_box(self) -> ScanOutcome:
        return self._finalize_current_box("")

    def reset_current_box(
        self, reason: str = "manual reset"
    ) -> BoxState:
        """逻辑作废当前未完成箱，并以相同目标数量初始化空箱。"""

        current = self.state
        order = self.database.get_order(current.offline_order_no)
        if int(order["printed"]) or order["status"] in {
            "PRINTED",
            "PDF_ONLY",
        }:
            raise ValueError(
                "已完成箱不能重置，请通过历史记录查看或补打。"
            )

        voided_count = self.database.reset_order(
            current.offline_order_no,
            reason=reason,
        )
        self.logger.warning(
            "当前箱已重置：order=%s voided_records=%s reason=%s",
            current.offline_order_no,
            voided_count,
            reason,
        )
        self._order = self._create_next_order(current.required_count)
        return self.state

    def reprint(self, offline_order_no: str) -> PrintResult:
        order = self.database.get_order(offline_order_no)
        pdf_path = Path(order["pdf_path"])
        result = self.printer.print_pdf(pdf_path)
        if result.success and not result.skipped:
            self.database.mark_printed(offline_order_no, reprint=True)
        elif not result.success:
            self.database.update_order_status(
                offline_order_no,
                "PRINT_FAILED",
                print_error=result.message,
            )
        return result

    def _reject(
        self,
        barcode: str,
        scan_index: int,
        result: str,
        message: str,
        *,
        material: Material | None = None,
    ) -> ScanOutcome:
        self._record(
            barcode=barcode,
            scan_index=scan_index,
            result=result,
            message=message,
            material=material,
        )
        return ScanOutcome(False, result, message, barcode, self.state)

    def _record(
        self,
        *,
        barcode: str,
        scan_index: int,
        result: str,
        message: str,
        material: Material | None,
    ) -> None:
        current = self.state
        self.database.record_scan(
            offline_order_no=current.offline_order_no,
            box_no=current.box_no,
            barcode=barcode,
            scan_index=scan_index,
            result=result,
            message=message,
            material_code=material.material_code if material else "",
            material_name=material.material_name if material else "",
            customer_material_code=(
                material.customer_material_code if material else ""
            ),
            computer_name=self.computer_name,
            line_name=self.config.line_name,
            station_name=self.config.station_name,
        )

    def _finalize_current_box(self, triggering_barcode: str) -> ScanOutcome:
        current = self.state
        if not current.material_code or current.required_count <= 0:
            return ScanOutcome(
                False,
                "未满箱",
                "请先扫描第一件以识别物料和每箱数量",
                triggering_barcode,
                current,
            )
        if current.scanned_count != current.required_count:
            return ScanOutcome(
                False,
                "未满箱",
                f"还需扫描 {current.remaining_count} 件",
                triggering_barcode,
                current,
            )

        order = self.database.get_order(current.offline_order_no)
        pdf_path = Path(order["pdf_path"]) if order["pdf_path"] else None
        if pdf_path is None or not pdf_path.is_file():
            output_dir = Path(self.config.output_pdf_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = output_dir / f"{current.offline_order_no}.pdf"
            label = OfflineOrderLabel(
                offline_order_no=current.offline_order_no,
                material_code=current.material_code,
                material_name=current.material_name,
                customer_material_code=current.customer_material_code,
                quantity=current.required_count,
                production_time=datetime.now(),
                offline_location=self.config.station_name,
                reserved1_sub=self.config.reserved1_sub,
            )
            try:
                self.database.update_order_status(
                    current.offline_order_no, "PDF_GENERATING"
                )
                self.pdf_generator.generate(label, pdf_path)
                self.database.update_order_status(
                    current.offline_order_no,
                    "READY_TO_PRINT",
                    pdf_path=str(pdf_path.resolve()),
                    print_error="",
                )
            except Exception as exc:
                message = f"PDF生成失败：{exc}"
                self.logger.exception(message)
                self.database.update_order_status(
                    current.offline_order_no,
                    "PDF_FAILED",
                    print_error=message,
                )
                return ScanOutcome(
                    True,
                    "PDF生成失败",
                    message,
                    triggering_barcode,
                    self.state,
                    box_completed=True,
                )

        print_result = self.printer.print_pdf(pdf_path)
        if not print_result.success:
            self.database.update_order_status(
                current.offline_order_no,
                "PRINT_FAILED",
                pdf_path=str(pdf_path.resolve()),
                print_error=print_result.message,
            )
            return ScanOutcome(
                True,
                "打印失败",
                f"打印失败，PDF和数据已保留：{print_result.message}",
                triggering_barcode,
                self.state,
                box_completed=True,
            )

        if print_result.skipped:
            self.database.update_order_status(
                current.offline_order_no,
                "PDF_ONLY",
                pdf_path=str(pdf_path.resolve()),
                print_error="",
            )
        else:
            self.database.mark_printed(current.offline_order_no)
        completed_order = self.database.get_order(current.offline_order_no)
        self.mii_client.upload_offline_order(
            {
                **completed_order,
                "barcodes": [
                    row["barcode"]
                    for row in self.database.successful_scans(
                        current.offline_order_no
                    )
                ],
            }
        )
        self._order = self._create_next_order()
        result_name = "PDF已生成" if print_result.skipped else "打印完成"
        result_message = (
            "PDF已生成，macOS调试模式已跳过打印"
            if print_result.skipped
            else "PDF已生成，打印已发送"
        )
        return ScanOutcome(
            True,
            result_name,
            result_message,
            triggering_barcode,
            self.state,
            box_completed=True,
            printed=not print_result.skipped,
        )

    def _create_next_order(
        self, initial_required_count: int = 0
    ) -> dict[str, Any]:
        stamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        return self.database.create_order(
            f"EHX{stamp}",
            f"BOX{stamp}",
            max(0, int(initial_required_count)),
        )
