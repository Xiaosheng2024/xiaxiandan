"""EHX 下线防错程序 PySide6 全屏界面。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path
import platform

from PySide6.QtCore import QTimer, Qt
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .config import load_config
from .database import Database
from .materials import MaterialRepository
from .scanner_service import BoxState, ScannerService


STATUS_COLORS = {
    "待扫码": "#334155",
    "成功": "#15803d",
    "重复": "#b91c1c",
    "物料不一致": "#b91c1c",
    "格式错误": "#b91c1c",
    "未配置物料": "#b91c1c",
    "PDF生成失败": "#b91c1c",
    "打印失败": "#b45309",
    "打印完成": "#0369a1",
    "PDF已生成": "#0369a1",
}


class ErrorPopup(QDialog):
    """产线用非阻塞错误提示窗。"""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("扫码错误")
        self.setModal(False)
        self.setWindowModality(Qt.WindowModality.NonModal)
        self.setMinimumWidth(620)
        self.setStyleSheet(
            "QDialog { background: #fff7ed; border: 5px solid #b91c1c; }"
            "QLabel { color: #991b1b; }"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setFont(
            QFont("Microsoft YaHei", 28, QFont.Weight.Bold)
        )
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_label.setFont(QFont("Microsoft YaHei", 20))
        layout.addWidget(self.title_label)
        layout.addWidget(self.message_label)

    def set_error(self, title: str, message: str) -> None:
        self.title_label.setText(title)
        self.message_label.setText(message)
        self.adjustSize()

    def text(self) -> str:
        return self.title_label.text()


class MainWindow(QWidget):
    def __init__(self, service: ScannerService) -> None:
        super().__init__()
        self.service = service
        self.error_dialog: ErrorPopup | None = None
        self.error_close_timer = QTimer(self)
        self.error_close_timer.setSingleShot(True)
        self.error_close_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.error_close_timer.setInterval(3000)
        self.error_close_timer.timeout.connect(self._close_error_popup)
        self.setWindowTitle("EHX 下线防错程序")
        self.setStyleSheet(
            "QWidget { background: #f1f5f9; color: #0f172a; }"
            "QLineEdit { background: white; border: 3px solid #2563eb;"
            " border-radius: 8px; padding: 12px; }"
            "QPushButton { background: #1d4ed8; color: white; padding: 12px;"
            " border-radius: 7px; font-size: 18px; }"
            "QTableWidget { background: white; font-size: 15px; }"
        )
        self._build_ui()
        self._install_shortcuts()
        self._refresh_state()
        self._refresh_recent()
        self.focus_timer = QTimer(self)
        self.focus_timer.timeout.connect(self._ensure_scan_focus)
        self.focus_timer.start(800)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(14)

        title_row = QHBoxLayout()
        title = QLabel("EHX 下线防错")
        title.setFont(QFont("Microsoft YaHei", 28, QFont.Weight.Bold))
        title_row.addWidget(title)
        mode_text = (
            "macOS 调试模式：只生成PDF，不打印"
            if platform.system() == "Darwin"
            else "Windows 正式模式：生成PDF并打印"
        )
        mode_label = QLabel(mode_text)
        mode_label.setStyleSheet(
            "background: #dbeafe; color: #1e3a8a; padding: 10px;"
            " border-radius: 8px;"
        )
        mode_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        title_row.addWidget(mode_label)
        title_row.addStretch(1)
        self.progress_big_label = QLabel("0/0")
        self.progress_big_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress_big_label.setMinimumWidth(240)
        self.progress_big_label.setFont(
            QFont("Arial", 56, QFont.Weight.Black)
        )
        self.progress_big_label.setStyleSheet(
            "background: #ffffff; color: #0f172a;"
            " border: 3px solid #0f172a; border-radius: 12px;"
            " padding: 2px 18px;"
        )
        title_row.addWidget(self.progress_big_label)
        title_row.addStretch(1)
        history_button = QPushButton("历史查询 / 补打")
        history_button.clicked.connect(self._open_history)
        retry_button = QPushButton("重试满箱处理")
        retry_button.clicked.connect(self._retry_finalize)
        title_row.addWidget(history_button)
        title_row.addWidget(retry_button)
        root.addLayout(title_row)

        info = QGridLayout()
        info.setSpacing(12)
        self.material_value = self._card(info, 0, 0, "当前物料", "--", 2)
        self.order_value = self._card(info, 1, 0, "当前下线单号", "--", 2)
        self.required_value = self._card(info, 2, 0, "需扫数量", "0")
        self.scanned_value = self._card(info, 2, 1, "已扫数量", "0")
        self.remaining_value = self._card(info, 2, 2, "剩余数量", "0")
        root.addLayout(info)

        self.status_label = QLabel("待扫码")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(
            QFont("Microsoft YaHei", 30, QFont.Weight.Bold)
        )
        self.status_label.setMinimumHeight(72)
        root.addWidget(self.status_label)

        self.scan_input = QLineEdit()
        self.scan_input.setPlaceholderText("请扫描条码（扫码后自动回车处理）")
        self.scan_input.setFont(QFont("Consolas", 24))
        self.scan_input.returnPressed.connect(self._process_scan)
        root.addWidget(self.scan_input)

        recent_title = QLabel("最近扫码")
        recent_title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        root.addWidget(recent_title)
        self.recent_table = QTableWidget(0, 5)
        self.recent_table.setHorizontalHeaderLabels(
            ["时间", "完整条码", "物料号", "结果", "说明"]
        )
        self.recent_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.recent_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self.recent_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.recent_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        root.addWidget(self.recent_table, 1)

    def _card(
        self,
        layout: QGridLayout,
        row: int,
        column: int,
        caption: str,
        value: str,
        column_span: int = 1,
    ) -> QLabel:
        card = QWidget()
        card.setStyleSheet(
            "background: white; border: 1px solid #cbd5e1; border-radius: 10px;"
        )
        box = QVBoxLayout(card)
        label = QLabel(caption)
        label.setFont(QFont("Microsoft YaHei", 14))
        output = QLabel(value)
        output.setWordWrap(True)
        output.setFont(QFont("Microsoft YaHei", 27, QFont.Weight.Bold))
        box.addWidget(label)
        box.addWidget(output)
        layout.addWidget(card, row, column, 1, column_span)
        return output

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+Q"), self, activated=self.close)
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

    def _process_scan(self) -> None:
        previous_state = self.service.state
        barcode = self.scan_input.text()
        self.scan_input.clear()
        outcome = self.service.process_barcode(barcode)
        self._show_status(outcome.result, outcome.message)
        self._handle_outcome_error(outcome)
        self._refresh_outcome_state(previous_state, outcome)
        self._refresh_recent()
        self.scan_input.setFocus()

    def _retry_finalize(self) -> None:
        previous_state = self.service.state
        outcome = self.service.retry_current_box()
        self._show_status(outcome.result, outcome.message)
        self._handle_outcome_error(outcome)
        self._refresh_outcome_state(previous_state, outcome)
        self._refresh_recent()

    def _show_status(self, result: str, message: str) -> None:
        color = STATUS_COLORS.get(result, STATUS_COLORS["待扫码"])
        self.status_label.setText(f"{result}：{message}")
        self.status_label.setStyleSheet(
            f"background: {color}; color: white; border-radius: 10px;"
        )

    def _refresh_state(self, state: BoxState | None = None) -> None:
        state = state or self.service.state
        material = state.material_code or "等待首件扫码"
        if state.material_name:
            material += f"\n{state.material_name}"
        self.material_value.setText(material)
        self.order_value.setText(state.offline_order_no)
        self.required_value.setText(str(state.required_count))
        self.scanned_value.setText(str(state.scanned_count))
        self.remaining_value.setText(str(state.remaining_count))
        self.progress_big_label.setText(
            f"{state.scanned_count}/{state.required_count}"
        )
        if state.status != "SCANNING":
            self._show_status(state.status, "当前箱需要处理")

    def _refresh_recent(self) -> None:
        rows = self.service.database.recent_records(10)
        self.recent_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["scan_time"][11:19],
                row["barcode"],
                row["material_code"],
                row["result"],
                row["message"],
            ]
            for column, value in enumerate(values):
                self.recent_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )

    def _refresh_outcome_state(self, previous_state: BoxState, outcome: object) -> None:
        switched_to_new_box = (
            outcome.box_completed
            and outcome.state.offline_order_no
            != previous_state.offline_order_no
        )
        if not switched_to_new_box:
            self._refresh_state(outcome.state)
            return

        completed_state = replace(
            previous_state,
            scanned_count=previous_state.required_count,
            remaining_count=0,
        )
        self._refresh_state(completed_state)
        next_order_no = outcome.state.offline_order_no
        QTimer.singleShot(
            800,
            lambda: self._refresh_new_box_if_still_empty(next_order_no),
        )

    def _refresh_new_box_if_still_empty(self, order_no: str) -> None:
        current = self.service.state
        if (
            current.offline_order_no == order_no
            and current.scanned_count == 0
        ):
            self._refresh_state(current)

    def _open_history(self) -> None:
        HistoryDialog(self.service, self).exec()
        self.scan_input.setFocus()

    def _ensure_scan_focus(self) -> None:
        if QApplication.activeModalWidget() is None:
            self.scan_input.setFocus()

    def _handle_outcome_error(self, outcome: object) -> None:
        error_results = {
            "重复",
            "物料不一致",
            "格式错误",
            "未配置物料",
            "PDF生成失败",
            "打印失败",
            "待处理",
            "未满箱",
        }
        if not outcome.accepted or outcome.result in error_results:
            QApplication.beep()
            self.show_error_popup(outcome.result, outcome.message)

    def show_error_popup(self, title: str, message: str) -> None:
        """显示非阻塞错误窗口；新错误会更新内容并重置3秒计时。"""

        if self.error_dialog is None:
            self.error_dialog = ErrorPopup(self)
        self.error_dialog.set_error(title, message)
        self.error_dialog.show()
        self.error_dialog.raise_()
        self.error_close_timer.start()
        QTimer.singleShot(0, self._restore_scan_focus)

    def _close_error_popup(self) -> None:
        if self.error_dialog is not None:
            self.error_dialog.close()
        self._restore_scan_focus()

    def _restore_scan_focus(self) -> None:
        self.activateWindow()
        self.scan_input.setFocus()


class HistoryDialog(QDialog):
    def __init__(self, service: ScannerService, parent: QWidget | None = None):
        super().__init__(parent)
        self.service = service
        self.setWindowTitle("历史记录查询")
        self.resize(1100, 650)
        root = QVBoxLayout(self)

        controls = QHBoxLayout()
        self.query_type = QComboBox()
        self.query_type.addItems(["完整条码", "下线单号", "日期"])
        self.query_text = QLineEdit()
        self.query_text.setPlaceholderText("日期格式：YYYY-MM-DD")
        search_button = QPushButton("查询")
        search_button.clicked.connect(self._search)
        reprint_button = QPushButton("补打所选下线单")
        reprint_button.clicked.connect(self._reprint)
        open_pdf_button = QPushButton("打开PDF")
        open_pdf_button.clicked.connect(self._open_pdf)
        controls.addWidget(self.query_type)
        controls.addWidget(self.query_text, 1)
        controls.addWidget(search_button)
        controls.addWidget(open_pdf_button)
        controls.addWidget(reprint_button)
        root.addLayout(controls)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "下线单号",
                "箱号",
                "物料号",
                "物料名称",
                "完整条码",
                "顺序",
                "扫码时间",
                "结果",
                "已打印",
            ]
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        root.addWidget(self.table)

    def _search(self) -> None:
        value = self.query_text.text().strip()
        if not value:
            return
        selected = self.query_type.currentText()
        if selected == "完整条码":
            rows = self.service.database.history_by_barcode(value)
        elif selected == "下线单号":
            rows = self.service.database.history_by_order(value)
        else:
            try:
                date.fromisoformat(value)
            except ValueError:
                QMessageBox.warning(self, "日期错误", "请输入 YYYY-MM-DD")
                return
            rows = self.service.database.history_by_date(value)
        self._populate(rows)

    def _populate(self, rows: list[dict]) -> None:
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            values = [
                row["offline_order_no"],
                row["box_no"],
                row["material_code"],
                row["material_name"],
                row["barcode"],
                row["scan_index"],
                row["scan_time"],
                row["result"],
                "是" if row["printed"] else "否",
            ]
            for column, value in enumerate(values):
                self.table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )

    def _reprint(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "补打", "请先选择一条记录")
            return
        order_no = self.table.item(row, 0).text()
        result = self.service.reprint(order_no)
        if result.success:
            QMessageBox.information(self, "补打", "补打命令已提交")
        else:
            QMessageBox.warning(self, "补打失败", result.message)

    def _open_pdf(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "打开PDF", "请先选择一条记录")
            return
        order_no = self.table.item(row, 0).text()
        order = self.service.database.get_order(order_no)
        pdf_path = Path(order["pdf_path"])
        if not pdf_path.is_file():
            QMessageBox.warning(self, "打开PDF", "该下线单没有可用PDF")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path.resolve())))


def build_service(config_path: str | Path = "config.json") -> ScannerService:
    config_file = Path(config_path).expanduser().resolve()
    base_dir = config_file.parent
    config = load_config(config_file)

    def resolve_config_path(value: str) -> str:
        path = Path(value).expanduser()
        return str(path if path.is_absolute() else (base_dir / path).resolve())

    config = replace(
        config,
        template_path=resolve_config_path(config.template_path),
        output_pdf_dir=resolve_config_path(config.output_pdf_dir),
        database_path=resolve_config_path(config.database_path),
        material_excel_path=resolve_config_path(config.material_excel_path),
        barcode_output_dir=resolve_config_path(config.barcode_output_dir),
    )
    database = Database(config.database_path)
    materials = MaterialRepository(database, config.material_excel_path)
    return ScannerService(config, database, materials)
