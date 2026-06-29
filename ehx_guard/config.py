"""程序 JSON 配置读取。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeConfig:
    printer_name: str = ""
    template_path: str = "报交下线单模板.xlsx"
    output_pdf_dir: str = "output/pdf"
    database_path: str = "data/ehx_guard.db"
    reserved1_sub: str = "2918"
    box_scan_count: int = 6
    line_name: str = "EHX"
    station_name: str = "下线工位"
    material_excel_path: str = "EHX物料号匹配.xlsx"
    mii_enabled: bool = False
    mii_base_url: str = ""
    mii_token: str = ""
    barcode_mode: str = "image"
    barcode_show_text: bool = True
    barcode_output_dir: str = "output/barcodes"
    pdf_renderer: str = "excel_com"
    print_method: str = "excel_com"
    debug_no_print_on_mac: bool = True
    mac_pdf_renderer: str = "reportlab"
    windows_pdf_renderer: str = "excel_com"
    windows_print_method: str = "excel_com"


def load_config(path: str | Path = "config.json") -> RuntimeConfig:
    config_path = Path(path)
    if not config_path.is_file():
        return RuntimeConfig()
    with config_path.open("r", encoding="utf-8") as source:
        raw = json.load(source)
    if not isinstance(raw, dict):
        raise ValueError("config.json 顶层必须是 JSON 对象")
    defaults = RuntimeConfig()
    return RuntimeConfig(
        printer_name=str(raw.get("printer_name", defaults.printer_name)).strip(),
        template_path=str(
            raw.get("template_path", defaults.template_path)
        ).strip(),
        output_pdf_dir=str(
            raw.get("output_pdf_dir", defaults.output_pdf_dir)
        ).strip(),
        database_path=str(
            raw.get("database_path", defaults.database_path)
        ).strip(),
        reserved1_sub=str(
            raw.get("reserved1_sub", defaults.reserved1_sub)
        ).strip()
        or defaults.reserved1_sub,
        box_scan_count=max(
            1, int(raw.get("box_scan_count", defaults.box_scan_count))
        ),
        line_name=str(raw.get("line_name", defaults.line_name)).strip(),
        station_name=str(raw.get("station_name", defaults.station_name)).strip(),
        material_excel_path=str(
            raw.get("material_excel_path", defaults.material_excel_path)
        ).strip(),
        mii_enabled=bool(raw.get("mii_enabled", defaults.mii_enabled)),
        mii_base_url=str(
            raw.get("mii_base_url", defaults.mii_base_url)
        ).strip(),
        mii_token=str(raw.get("mii_token", defaults.mii_token)).strip(),
        barcode_mode=str(
            raw.get("barcode_mode", defaults.barcode_mode)
        ).strip().lower(),
        barcode_show_text=bool(
            raw.get("barcode_show_text", defaults.barcode_show_text)
        ),
        barcode_output_dir=str(
            raw.get("barcode_output_dir", defaults.barcode_output_dir)
        ).strip(),
        pdf_renderer=str(
            raw.get("pdf_renderer", defaults.pdf_renderer)
        ).strip().lower(),
        print_method=str(
            raw.get("print_method", defaults.print_method)
        ).strip().lower(),
        debug_no_print_on_mac=bool(
            raw.get(
                "debug_no_print_on_mac",
                defaults.debug_no_print_on_mac,
            )
        ),
        mac_pdf_renderer=str(
            raw.get("mac_pdf_renderer", defaults.mac_pdf_renderer)
        ).strip().lower(),
        windows_pdf_renderer=str(
            raw.get(
                "windows_pdf_renderer", defaults.windows_pdf_renderer
            )
        ).strip().lower(),
        windows_print_method=str(
            raw.get(
                "windows_print_method", defaults.windows_print_method
            )
        ).strip().lower(),
    )
