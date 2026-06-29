"""命令行生成一张 A5 下线单 PDF。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from ehx_guard.config import load_config
from ehx_guard.pdf_generator import A5PdfGenerator, OfflineOrderLabel


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 EHX A5 下线单 PDF")
    parser.add_argument("data_json", type=Path, help="下线单 JSON 数据文件")
    parser.add_argument("output_pdf", type=Path, help="输出 PDF 路径")
    parser.add_argument("--config", type=Path, default=Path("config.json"))
    parser.add_argument("--template", type=Path, help="Excel 模板路径")
    parser.add_argument("--soffice", type=Path, help="soffice.exe 路径")
    args = parser.parse_args()

    with args.data_json.open("r", encoding="utf-8") as source:
        data = json.load(source)
    data["production_time"] = datetime.fromisoformat(data["production_time"])

    config = load_config(args.config)
    if not str(data.get("reserved1_sub", "")).strip():
        data["reserved1_sub"] = config.reserved1_sub
    template = args.template or Path(config.template_path)
    soffice = args.soffice or (
        Path(config.libreoffice_path) if config.libreoffice_path else None
    )
    generator = A5PdfGenerator(
        template,
        soffice_path=soffice,
        enable_office_pdf_on_mac=config.enable_office_pdf_on_mac,
    )
    result = generator.generate(OfflineOrderLabel(**data), args.output_pdf)
    print(result)


if __name__ == "__main__":
    main()
