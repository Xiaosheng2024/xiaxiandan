"""Windows Excel COM 打印与 macOS无打印适配器。"""

from __future__ import annotations

import logging
import os
import gc
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


def _is_windows() -> bool:
    return os.name == "nt"


@dataclass(frozen=True)
class PrintResult:
    success: bool
    pdf_path: Path
    printer_name: str
    message: str
    printed_at: datetime | None = None
    skipped: bool = False


class ExcelComPrinter:
    """通过 Microsoft Excel COM 直接打印 PDF 同名的 XLSX 模板副本。"""

    def __init__(
        self,
        *,
        printer_name: str = "",
        logger: logging.Logger | None = None,
    ) -> None:
        self.printer_name = printer_name.strip()
        self.logger = logger or logging.getLogger("ehx_guard.printing")

    def print_pdf(
        self,
        pdf_path: str | Path,
        *,
        printer_name: str | None = None,
    ) -> PrintResult:
        path = Path(pdf_path).expanduser().resolve()
        workbook_path = path.with_suffix(".xlsx")
        selected_printer = (
            self.printer_name if printer_name is None else printer_name.strip()
        )
        if not path.is_file():
            return self._failure(path, selected_printer, "PDF 文件不存在")
        if not workbook_path.is_file():
            return self._failure(
                path, selected_printer, f"打印模板副本不存在：{workbook_path}"
            )
        if not _is_windows():
            return self._failure(
                path, selected_printer, "Excel COM 打印仅支持 Windows"
            )
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            return self._failure(path, selected_printer, f"未安装 pywin32：{exc}")

        excel = None
        workbook = None
        worksheet = None
        pythoncom.CoInitialize()
        try:
            excel = win32com.client.DispatchEx("Excel.Application")
            excel.Visible = False
            excel.DisplayAlerts = False
            workbook = excel.Workbooks.Open(
                str(workbook_path), UpdateLinks=0, ReadOnly=True
            )
            worksheet = workbook.Worksheets(1)
            self._print_worksheet(worksheet, selected_printer)
        except Exception as exc:
            self.logger.exception(
                "Excel COM 打印失败 pdf=%s xlsx=%s printer=%s",
                path,
                workbook_path,
                selected_printer or "<默认打印机>",
            )
            return self._failure(
                path, selected_printer, f"Excel COM 打印失败：{exc}"
            )
        finally:
            if workbook is not None:
                try:
                    workbook.Close(SaveChanges=False)
                except Exception:
                    self.logger.exception("关闭 Excel 打印工作簿失败")
            if excel is not None:
                try:
                    excel.Quit()
                except Exception:
                    self.logger.exception("退出 Excel 打印进程失败")
            workbook = None
            worksheet = None
            excel = None
            gc.collect()
            pythoncom.CoUninitialize()

        return PrintResult(
            success=True,
            pdf_path=path,
            printer_name=selected_printer,
            message="Excel COM 打印命令已提交",
            printed_at=datetime.now(),
        )

    def _failure(
        self, path: Path, printer_name: str, message: str
    ) -> PrintResult:
        self.logger.error(
            "Excel COM 打印失败 pdf=%s printer=%s message=%s；文件已保留",
            path,
            printer_name or "<默认打印机>",
            message,
        )
        return PrintResult(
            success=False,
            pdf_path=path,
            printer_name=printer_name,
            message=message,
        )

    @staticmethod
    def _print_worksheet(worksheet: object, printer_name: str) -> None:
        """空名称使用默认打印机，否则传递完整 Windows 打印机名称。"""

        if printer_name:
            worksheet.PrintOut(ActivePrinter=printer_name)
        else:
            worksheet.PrintOut()


class DebugNoPrintPrinter:
    """macOS 开发模式：明确跳过真实打印，但不阻塞下一箱。"""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("ehx_guard.printing")

    def print_pdf(
        self,
        pdf_path: str | Path,
        *,
        printer_name: str | None = None,
    ) -> PrintResult:
        path = Path(pdf_path).expanduser().resolve()
        if not path.is_file():
            return PrintResult(
                success=False,
                pdf_path=path,
                printer_name="",
                message="PDF 文件不存在",
            )
        message = "macOS调试模式：已跳过真实打印"
        self.logger.info("%s pdf=%s", message, path)
        return PrintResult(
            success=True,
            pdf_path=path,
            printer_name="",
            message=message,
            skipped=True,
        )
