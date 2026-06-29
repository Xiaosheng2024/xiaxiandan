"""检查 EHX 下线防错程序的 Windows 部署运行环境。"""

from __future__ import annotations

import argparse
import importlib.util
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ehx_guard.config import load_config
from ehx_guard.pdf_generator import is_excel_com_available


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _resolve_project_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _check_writable(directory: Path) -> tuple[bool, str]:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=directory, delete=True):
            pass
        return True, str(directory.resolve())
    except OSError as exc:
        return False, f"{directory.resolve()}：{exc}"


def _check_sqlite(database_path: Path) -> tuple[bool, str]:
    try:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        if database_path.exists():
            connection = sqlite3.connect(
                f"file:{database_path.resolve()}?mode=rw", uri=True, timeout=5
            )
            check = connection.execute("PRAGMA quick_check").fetchone()
            connection.close()
            return check == ("ok",), f"现有数据库可读写：{database_path.resolve()}"
        with tempfile.NamedTemporaryFile(
            dir=database_path.parent, suffix=".db", delete=True
        ) as temporary:
            connection = sqlite3.connect(temporary.name, timeout=5)
            connection.execute("CREATE TABLE runtime_check (id INTEGER)")
            connection.commit()
            connection.close()
        return True, f"数据库尚未创建，目录可创建 SQLite：{database_path.resolve()}"
    except (OSError, sqlite3.Error) as exc:
        return False, f"{database_path.resolve()}：{exc}"


def _printer_status(configured_name: str) -> tuple[str, list[str], bool | None]:
    if os.name == "nt":
        try:
            import win32print

            default = win32print.GetDefaultPrinter()
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            printers = sorted(
                {entry[2] for entry in win32print.EnumPrinters(flags)}
            )
        except Exception as exc:
            return f"检测失败：{exc}", [], None
    else:
        default = "未检测到"
        printers = []
        lpstat = shutil.which("lpstat")
        if lpstat:
            try:
                result = subprocess.run(
                    [lpstat, "-d"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                if result.returncode == 0:
                    default = result.stdout.strip()
                result = subprocess.run(
                    [lpstat, "-p"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                printers = [
                    line.split()[1]
                    for line in result.stdout.splitlines()
                    if line.startswith("printer ") and len(line.split()) > 1
                ]
            except (OSError, subprocess.TimeoutExpired):
                pass
    exists = configured_name in printers if configured_name else None
    return default, printers, exists


def _configured_printer_check(
    printer_name: str, exists: bool | None
) -> str:
    if not printer_name:
        return "未配置，将使用 Windows 默认打印机"
    if exists is True:
        return f"已找到指定打印机：{printer_name}"
    if exists is False:
        return (
            f"未找到指定打印机“{printer_name}”，"
            "请运行 Get-Printer | Select-Object Name，"
            "并修改 config.json"
        )
    return "无法读取打印机列表，请检查 pywin32 和打印服务"


def collect_runtime(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    template_path = _resolve_project_path(config.template_path)
    output_dir = _resolve_project_path(config.output_pdf_dir)
    database_path = _resolve_project_path(config.database_path)
    logs_dir = PROJECT_ROOT / "logs"

    excel_com_ok, excel_com_detail = is_excel_com_available()
    default_printer, printers, configured_printer_exists = _printer_status(
        config.printer_name
    )
    output_writable, output_detail = _check_writable(output_dir)
    logs_writable, logs_detail = _check_writable(logs_dir)
    sqlite_ok, sqlite_detail = _check_sqlite(database_path)
    configured_printer_check = _configured_printer_check(
        config.printer_name, configured_printer_exists
    )

    return {
        "Windows/系统版本": platform.platform(),
        "Python版本": sys.version.replace("\n", " "),
        "Microsoft Excel COM可用": excel_com_ok,
        "Microsoft Excel COM详情": excel_com_detail,
        "pywin32已安装": _module_available("win32com"),
        "正式打印方式": "Excel COM Worksheet.PrintOut",
        "条码模式": config.barcode_mode,
        "PDF渲染器": config.pdf_renderer,
        "打印方式": config.print_method,
        "reportlab已安装": _module_available("reportlab"),
        "openpyxl已安装": _module_available("openpyxl"),
        "当前默认打印机": default_printer,
        "config printer_name": config.printer_name or "未配置（使用默认打印机）",
        "config打印机存在": configured_printer_exists,
        "指定打印机检查": configured_printer_check,
        "检测到的打印机": printers,
        "模板文件存在": template_path.is_file(),
        "模板路径": str(template_path.resolve()),
        "output/pdf可写": output_writable,
        "output/pdf详情": output_detail,
        "logs可写": logs_writable,
        "logs详情": logs_detail,
        "SQLite数据库可访问": sqlite_ok,
        "SQLite详情": sqlite_detail,
        "当前平台PDF策略": (
            "Excel COM -> ReportLab fallback"
            if os.name == "nt"
            else (
                "ReportLab fallback（macOS 仅开发验证）"
            )
        ),
        "Windows必需项": (
            "Excel COM、pywin32、打印机驱动、模板访问权限"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="检查 EHX 程序运行环境")
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config.json",
        help="配置文件路径",
    )
    args = parser.parse_args()
    result = collect_runtime(args.config)
    for key, value in result.items():
        if isinstance(value, list):
            value = "、".join(value) if value else "无"
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
