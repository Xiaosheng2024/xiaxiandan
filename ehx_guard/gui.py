"""EHX 下线防错程序 PySide6 全屏界面。"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut
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
}


class MainWindow(QWidget):
    def __init__(self, service: ScannerService) -> None:
        super().__init__()
        self.service = service
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
        title_row.addStretch()
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
        barcode = self.scan_input.text()
        self.scan_input.clear()
        outcome = self.service.process_barcode(barcode)
        self._show_status(outcome.result, outcome.message)
        if not outcome.accepted:
            QApplication.beep()
        self._refresh_state(outcome.state)
        self._refresh_recent()
        self.scan_input.setFocus()

    def _retry_finalize(self) -> None:
        outcome = self.service.retry_current_box()
        self._show_status(outcome.result, outcome.message)
        if not outcome.printed:
            QApplication.beep()
        self._refresh_state(outcome.state)
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

    def _open_history(self) -> None:
        HistoryDialog(self.service, self).exec()
        self.scan_input.setFocus()

    def _ensure_scan_focus(self) -> None:
        if QApplication.activeModalWidget() is None:
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
        controls.addWidget(self.query_type)
        controls.addWidget(self.query_text, 1)
        controls.addWidget(search_button)
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
    )
    database = Database(config.database_path)
    materials = MaterialRepository(database, config.material_excel_path)
    return ScannerService(config, database, materials)
