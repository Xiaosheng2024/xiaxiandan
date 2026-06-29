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
from ehx_guard.pdf_generator import find_soffice
from ehx_guard.printing import find_sumatra


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _resolve_project_path(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def _check_libreoffice(configured_path: str) -> tuple[bool, str, str]:
    path = find_soffice(configured_path or None)
    if path is None:
        return False, "未找到 soffice.exe", ""
    if platform.system() == "Darwin":
        return (
            True,
            "已检测到路径；macOS 开发环境不执行 soffice，正式转换仅在 Windows 验收",
            str(path),
        )
    if os.name != "nt":
        return True, "已检测到路径；当前非 Windows，未执行转换测试", str(path)
    try:
        result = subprocess.run(
            [str(path), "--headless", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"命令执行失败：{exc}", str(path)
    detail = (result.stdout or result.stderr or "无版本信息").strip()
    return result.returncode == 0, detail, str(path)


def _check_sumatra(configured_path: str) -> tuple[bool, str, str]:
    path = find_sumatra(configured_path or None)
    if path is None:
        return False, "未找到 SumatraPDF.exe", ""
    if os.name != "nt":
        return True, "已检测到路径；非 Windows 环境不执行打印测试", str(path)
    return True, "路径可访问；实际静默打印需用现场打印机验收", str(path)


def _check_code128_font() -> tuple[bool, str]:
    candidates: list[Path] = []
    if os.name == "nt":
        fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        candidates.extend(
            fonts_dir / name
            for name in (
                "code128.ttf",
                "code128-1.ttf",
                "Code128.ttf",
                "CODE128.TTF",
            )
        )
        try:
            import winreg

            key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                index = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    if "code" in name.lower() and "128" in name.lower():
                        return True, f"注册字体：{name} ({value})"
                    index += 1
        except (ImportError, OSError):
            pass
    else:
        for fonts_dir in (
            Path("/Library/Fonts"),
            Path.home() / "Library/Fonts",
            Path("/usr/share/fonts"),
        ):
            if fonts_dir.is_dir():
                try:
                    candidates.extend(
                        path
                        for path in fonts_dir.iterdir()
                        if "code" in path.name.lower()
                        and "128" in path.name.lower()
                    )
                except OSError:
                    pass
    for candidate in candidates:
        if candidate.is_file():
            return True, str(candidate)
    return False, "未检测到 Code128 字体；Windows 正式部署必须安装"


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


def collect_runtime(config_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    template_path = _resolve_project_path(config.template_path)
    output_dir = _resolve_project_path(config.output_pdf_dir)
    database_path = _resolve_project_path(config.database_path)
    logs_dir = PROJECT_ROOT / "logs"

    libreoffice_ok, libreoffice_detail, libreoffice_path = _check_libreoffice(
        config.libreoffice_path
    )
    sumatra_ok, sumatra_detail, sumatra_path = _check_sumatra(
        config.sumatra_path
    )
    code128_ok, code128_detail = _check_code128_font()
    default_printer, printers, configured_printer_exists = _printer_status(
        config.printer_name
    )
    output_writable, output_detail = _check_writable(output_dir)
    logs_writable, logs_detail = _check_writable(logs_dir)
    sqlite_ok, sqlite_detail = _check_sqlite(database_path)

    return {
        "Windows/系统版本": platform.platform(),
        "Python版本": sys.version.replace("\n", " "),
        "LibreOffice找到": libreoffice_ok,
        "LibreOffice路径": libreoffice_path or "未找到",
        "LibreOffice详情": libreoffice_detail,
        "SumatraPDF找到": sumatra_ok,
        "SumatraPDF路径": sumatra_path or "未找到",
        "SumatraPDF详情": sumatra_detail,
        "Code128字体检测到": code128_ok,
        "Code128字体详情": code128_detail,
        "reportlab已安装": _module_available("reportlab"),
        "openpyxl已安装": _module_available("openpyxl"),
        "当前默认打印机": default_printer,
        "config printer_name": config.printer_name or "未配置（使用默认打印机）",
        "config打印机存在": configured_printer_exists,
        "检测到的打印机": printers,
        "模板文件存在": template_path.is_file(),
        "模板路径": str(template_path.resolve()),
        "output/pdf可写": output_writable,
        "output/pdf详情": output_detail,
        "logs可写": logs_writable,
        "logs详情": logs_detail,
        "SQLite数据库可访问": sqlite_ok,
        "SQLite详情": sqlite_detail,
        "enable_office_pdf_on_mac": config.enable_office_pdf_on_mac,
        "当前平台PDF策略": (
            "LibreOffice -> ReportLab fallback"
            if os.name == "nt"
            else (
                "LibreOffice -> ReportLab fallback（已由配置显式开启）"
                if config.enable_office_pdf_on_mac
                else "ReportLab fallback（macOS 默认跳过 soffice）"
            )
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
