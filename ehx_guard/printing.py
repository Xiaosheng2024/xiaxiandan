"""Windows 下使用 SumatraPDF 静默打印。"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class PrintResult:
    success: bool
    pdf_path: Path
    printer_name: str
    message: str
    printed_at: datetime | None = None


def find_sumatra(explicit_path: str | Path | None = None) -> Path | None:
    if explicit_path:
        candidate = Path(explicit_path).expanduser().resolve()
        return candidate if candidate.is_file() else None
    discovered = shutil.which("SumatraPDF") or shutil.which("SumatraPDF.exe")
    if discovered:
        return Path(discovered).resolve()
    for candidate in (
        Path(r"C:\Program Files\SumatraPDF\SumatraPDF.exe"),
        Path(r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe"),
    ):
        if candidate.is_file():
            return candidate.resolve()
    return None


class SumatraPdfPrinter:
    """打印失败返回失败结果；绝不删除 PDF，由业务层决定是否补打。"""

    def __init__(
        self,
        *,
        sumatra_path: str | Path | None = None,
        printer_name: str = "",
        logger: logging.Logger | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        self.sumatra_path = find_sumatra(sumatra_path)
        self.printer_name = printer_name.strip()
        self.logger = logger or logging.getLogger("ehx_guard.printing")
        self.timeout_seconds = timeout_seconds

    def print_pdf(
        self,
        pdf_path: str | Path,
        *,
        printer_name: str | None = None,
    ) -> PrintResult:
        path = Path(pdf_path).expanduser().resolve()
        selected_printer = (
            self.printer_name if printer_name is None else printer_name.strip()
        )
        if not path.is_file():
            return self._failure(path, selected_printer, "PDF 文件不存在")
        if os.name != "nt":
            return self._failure(
                path, selected_printer, "SumatraPDF 静默打印仅支持 Windows"
            )
        if not self.sumatra_path:
            return self._failure(path, selected_printer, "未找到 SumatraPDF.exe")

        if selected_printer:
            command = [
                str(self.sumatra_path),
                "-print-to",
                selected_printer,
                "-silent",
                str(path),
            ]
        else:
            command = [
                str(self.sumatra_path),
                "-print-to-default",
                "-silent",
                str(path),
            ]
        startup_info = subprocess.STARTUPINFO()
        startup_info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                startupinfo=startup_info,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return self._failure(path, selected_printer, f"打印命令异常：{exc}")

        detail = (result.stderr or result.stdout or "").strip()
        self.logger.info(
            "SumatraPDF command=%s returncode=%s stdout=%s stderr=%s",
            command,
            result.returncode,
            result.stdout.strip(),
            result.stderr.strip(),
        )
        if result.returncode != 0:
            return self._failure(
                path,
                selected_printer,
                f"打印失败，退出码 {result.returncode}：{detail or '无详情'}",
            )
        return PrintResult(
            success=True,
            pdf_path=path,
            printer_name=selected_printer,
            message="打印命令已成功提交",
            printed_at=datetime.now(),
        )

    def _failure(
        self, path: Path, printer_name: str, message: str
    ) -> PrintResult:
        self.logger.error(
            "PDF 打印失败 pdf=%s printer=%s message=%s；PDF 已保留",
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
