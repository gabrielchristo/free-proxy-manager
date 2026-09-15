from __future__ import annotations

import httpx
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from client_lib.api import PROXY_TABLE_COLUMNS, fetch_all_proxies, fetch_proxies_page, format_proxy_row
from gui.workers import AsyncWorker


class ProxiesTab(QWidget):
    def __init__(self, manager_url_getter, parent=None) -> None:
        super().__init__(parent)
        self.manager_url_getter = manager_url_getter
        self.worker: AsyncWorker | None = None
        self.total = 0
        self.current_offset = 0
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        filters_box = QGroupBox("Filters")
        grid = QGridLayout(filters_box)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(8)

        self.protocol = QComboBox()
        self.protocol.addItems(["", "http", "https", "socks4", "socks5"])
        self.status = QComboBox()
        self.status.addItems(
            ["", "HEALTHY", "DEGRADED", "DEAD", "NEW", "CHECKING", "DISABLED"]
        )
        self.country = QLineEdit()
        self.country_code = QLineEdit()
        self.country_code.setMaxLength(2)
        self.max_latency = QDoubleSpinBox()
        self.max_latency.setRange(0.0, 60000.0)
        self.max_latency.setSpecialValueText("(none)")
        self.max_latency.setValue(0.0)
        self.anonymous = QCheckBox("Anonymous only")
        self.min_score = QDoubleSpinBox()
        self.min_score.setRange(0.0, 100.0)
        self.min_score.setSpecialValueText("(none)")
        self.min_score.setValue(0.0)
        self.page_size = QSpinBox()
        self.page_size.setRange(1, 100)
        self.page_size.setValue(100)
        self.load_all = QCheckBox("Load all pages (may take a while)")

        fields = [
            ("Protocol", self.protocol),
            ("Status", self.status),
            ("Country", self.country),
            ("Country code", self.country_code),
            ("Max latency (ms)", self.max_latency),
            ("Min score", self.min_score),
            ("Page size", self.page_size),
            ("", self.anonymous),
        ]
        for index, (label, widget) in enumerate(fields):
            row, col = divmod(index, 2)
            base_col = col * 2
            if label:
                grid.addWidget(QLabel(label), row, base_col)
                grid.addWidget(widget, row, base_col + 1)
            else:
                grid.addWidget(widget, row, base_col, 1, 2)

        grid.addWidget(self.load_all, 4, 0, 1, 4)

        root.addWidget(filters_box)

        actions = QHBoxLayout()
        self.load_button = QPushButton("Load")
        self.load_button.setObjectName("primaryButton")
        self.load_button.clicked.connect(self.load_proxies)
        self.prev_button = QPushButton("Previous page")
        self.prev_button.clicked.connect(self.previous_page)
        self.next_button = QPushButton("Next page")
        self.next_button.clicked.connect(self.next_page)
        self.status_label = QLabel("No data loaded")
        self.status_label.setObjectName("statusLabel")
        actions.addWidget(self.load_button)
        actions.addWidget(self.prev_button)
        actions.addWidget(self.next_button)
        actions.addWidget(self.status_label, stretch=1)
        root.addLayout(actions)

        self.table = QTableWidget()
        self.table.setColumnCount(len(PROXY_TABLE_COLUMNS))
        self.table.setHorizontalHeaderLabels(PROXY_TABLE_COLUMNS)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setMinimumHeight(520)
        self.table.horizontalHeader().setStretchLastSection(True)
        root.addWidget(self.table, stretch=1)

    def _filters(self) -> dict:
        filters = {}
        protocol = self.protocol.currentText().strip()
        status = self.status.currentText().strip()
        country = self.country.text().strip()
        country_code = self.country_code.text().strip().upper()
        if protocol:
            filters["protocol"] = protocol
        if status:
            filters["status"] = status
        if country:
            filters["country"] = country
        if country_code:
            filters["country_code"] = country_code
        if self.max_latency.value() > 0:
            filters["max_latency"] = self.max_latency.value()
        if self.anonymous.isChecked():
            filters["anonymous"] = True
        if self.min_score.value() > 0:
            filters["min_score"] = self.min_score.value()
        return filters

    def load_proxies(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        manager_url = self.manager_url_getter().strip()
        if not manager_url:
            QMessageBox.warning(self, "Missing URL", "Set the manager URL at the top of the window.")
            return

        self.current_offset = 0
        self.load_button.setEnabled(False)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.status_label.setText("Loading...")

        filters = self._filters()
        page_size = self.page_size.value()
        load_all = self.load_all.isChecked()

        async def task() -> tuple[list[dict], int]:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if load_all:
                    items, total, error = await fetch_all_proxies(
                        client,
                        manager_url,
                        page_size=page_size,
                        **filters,
                    )
                    if error:
                        raise RuntimeError(error)
                    return items, total

                items, total, error = await fetch_proxies_page(
                    client,
                    manager_url,
                    limit=page_size,
                    offset=self.current_offset,
                    **filters,
                )
                if error:
                    raise RuntimeError(error)
                return items, total

        self.worker = AsyncWorker(task, parent=self)
        self.worker.finished_ok.connect(self._on_loaded)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def previous_page(self) -> None:
        page_size = self.page_size.value()
        if self.current_offset <= 0:
            return
        self.current_offset = max(0, self.current_offset - page_size)
        self._load_page()

    def next_page(self) -> None:
        page_size = self.page_size.value()
        if self.current_offset + page_size >= self.total:
            return
        self.current_offset += page_size
        self._load_page()

    def _load_page(self) -> None:
        if self.load_all.isChecked():
            self.load_proxies()
            return

        manager_url = self.manager_url_getter().strip()
        filters = self._filters()
        page_size = self.page_size.value()

        async def task() -> tuple[list[dict], int]:
            async with httpx.AsyncClient(timeout=30.0) as client:
                items, total, error = await fetch_proxies_page(
                    client,
                    manager_url,
                    limit=page_size,
                    offset=self.current_offset,
                    **filters,
                )
                if error:
                    raise RuntimeError(error)
                return items, total

        self.load_button.setEnabled(False)
        self.worker = AsyncWorker(task, parent=self)
        self.worker.finished_ok.connect(self._on_loaded)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _populate_table(self, items: list[dict]) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(items))
        for row_index, item in enumerate(items):
            values = format_proxy_row(item)
            for col_index, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row_index, col_index, cell)
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)

    def _on_loaded(self, payload: tuple[list[dict], int]) -> None:
        items, total = payload
        self.total = total
        self._populate_table(items)
        page_size = self.page_size.value()
        start = self.current_offset + 1 if items else 0
        end = self.current_offset + len(items)
        self.status_label.setText(f"Showing {start}-{end} of {total} proxies")
        self.load_button.setEnabled(True)
        self.prev_button.setEnabled(self.current_offset > 0 and not self.load_all.isChecked())
        self.next_button.setEnabled(
            not self.load_all.isChecked() and self.current_offset + page_size < total
        )

    def _on_failed(self, error: str) -> None:
        self.load_button.setEnabled(True)
        self.status_label.setText("Load failed")
        QMessageBox.warning(self, "Load failed", error)
