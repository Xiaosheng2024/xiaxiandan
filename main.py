"""EHX 下线防错程序启动入口。"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from ehx_guard.gui import MainWindow, build_service


APP_ROOT = Path(__file__).resolve().parent


def _configure_logging() -> None:
    log_path = APP_ROOT / "logs/ehx_guard.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path, maxBytes=3 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def main() -> int:
    _configure_logging()
    application = QApplication(sys.argv)
    application.setApplicationName("EHX下线防错")
    try:
        service = build_service(APP_ROOT / "config.json")
        window = MainWindow(service)
        window.showFullScreen()
        return application.exec()
    except Exception as exc:
        logging.getLogger(__name__).exception("程序启动失败")
        QMessageBox.critical(None, "启动失败", str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
