"""EHX 下线防错程序启动入口。"""

from __future__ import annotations

import faulthandler
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import BinaryIO

from PySide6.QtWidgets import QApplication, QMessageBox

from ehx_guard.gui import MainWindow, build_service


APP_ROOT = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
_CRASH_LOG_STREAM: BinaryIO | None = None


def _configure_logging() -> None:
    global _CRASH_LOG_STREAM
    log_path = APP_ROOT / "logs/ehx_guard.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path, maxBytes=3 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    crash_log_path = APP_ROOT / "logs/ehx_guard_crash.log"
    _CRASH_LOG_STREAM = crash_log_path.open("ab")
    faulthandler.enable(_CRASH_LOG_STREAM, all_threads=True)


def _handle_unexpected_exception(
    exception_type: type[BaseException],
    exception: BaseException,
    traceback: object,
) -> None:
    """记录 GUI 回调等位置未捕获的异常，避免 windowed EXE 静默失败。"""

    logging.getLogger(__name__).critical(
        "程序发生未处理异常",
        exc_info=(exception_type, exception, traceback),
    )
    application = QApplication.instance()
    if application is not None:
        QMessageBox.critical(
            None,
            "程序错误",
            f"{exception}\n\n详细信息已写入 logs/ehx_guard.log",
        )


def main() -> int:
    _configure_logging()
    sys.excepthook = _handle_unexpected_exception
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
