from __future__ import annotations

from typing import Any

import httpx
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from client_lib.api import fetch_health, fetch_stats
from client_lib.models import iso_value
from gui.workers import AsyncWorker

POOL_FIELDS = [
    ("healthy", "Healthy"),
    ("degraded", "Degraded"),
    ("dead", "Dead"),
    ("new", "New"),
    ("checking", "Checking"),
    ("disabled", "Disabled"),
    ("in_cooldown", "In cooldown"),
]

SOURCE_COLUMNS = [
    "name",
    "enabled",
    "proxies_found",
    "valid_proxies",
    "success_rate",
    "last_run",
    "last_success",
    "last_error",
]


class OverviewTab(QWidget):
    def __init__(self, manager_url_getter, parent=None) -> None:
        super().__init__(parent)
        self.manager_url_getter = manager_url_getter
        self.worker: AsyncWorker | None = None
        self._pool_labels: dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.setObjectName("primaryButton")
        self.refresh_button.clicked.connect(self.refresh)
        self.status_label = QLabel("Click Refresh to load /health and /stats")
        self.status_label.setObjectName("statusLabel")
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.status_label, stretch=1)
        root.addLayout(actions)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        layout = QVBoxLayout(content)

        health_box = QGroupBox("GET /health")
        health_layout = QVBoxLayout(health_box)
        health_summary = QFormLayout()
        self.health_status = QLabel("—")
        self.health_database = QLabel("—")
        health_summary.addRow("Status", self.health_status)
        health_summary.addRow("Database", self.health_database)
        health_layout.addLayout(health_summary)
        health_layout.addWidget(QLabel("Proxy pool"))
        health_layout.addLayout(self._build_pool_grid())
        layout.addWidget(health_box)

        stats_box = QGroupBox("GET /stats")
        stats_layout = QVBoxLayout(stats_box)
        stats_summary = QFormLayout()
        self.stats_total = QLabel("—")
        self.stats_http = QLabel("—")
        self.stats_https = QLabel("—")
        self.stats_avg_latency = QLabel("—")
        self.stats_success_rate = QLabel("—")
        stats_summary.addRow("Total proxies", self.stats_total)
        stats_summary.addRow("HTTP", self.stats_http)
        stats_summary.addRow("HTTPS", self.stats_https)
        stats_summary.addRow("Average latency (ms)", self.stats_avg_latency)
        stats_summary.addRow("Success rate (%)", self.stats_success_rate)
        stats_layout.addLayout(stats_summary)

        countries_box = QGroupBox("Proxies by country (usable)")
        countries_layout = QVBoxLayout(countries_box)
        self.countries_table = QTableWidget()
        self.countries_table.setColumnCount(2)
        self.countries_table.setHorizontalHeaderLabels(["Country", "Count"])
        self.countries_table.setAlternatingRowColors(True)
        self.countries_table.setMinimumHeight(160)
        self.countries_table.horizontalHeader().setStretchLastSection(True)
        countries_layout.addWidget(self.countries_table)
        stats_layout.addWidget(countries_box)

        sources_box = QGroupBox("Sources")
        sources_layout = QVBoxLayout(sources_box)
        self.sources_table = QTableWidget()
        self.sources_table.setColumnCount(len(SOURCE_COLUMNS))
        self.sources_table.setHorizontalHeaderLabels(SOURCE_COLUMNS)
        self.sources_table.setAlternatingRowColors(True)
        self.sources_table.setMinimumHeight(200)
        self.sources_table.horizontalHeader().setStretchLastSection(True)
        sources_layout.addWidget(self.sources_table)
        stats_layout.addWidget(sources_box)

        layout.addWidget(stats_box)
        layout.addStretch()

        scroll.setWidget(content)
        root.addWidget(scroll, stretch=1)

    def _build_pool_grid(self) -> QGridLayout:
        grid = QGridLayout()
        for index, (key, title) in enumerate(POOL_FIELDS):
            row, col = divmod(index, 4)
            label = QLabel(title)
            value = QLabel("—")
            value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._pool_labels[key] = value
            grid.addWidget(label, row, col * 2)
            grid.addWidget(value, row, col * 2 + 1)
        return grid

    def refresh(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        manager_url = self.manager_url_getter().strip()
        if not manager_url:
            QMessageBox.warning(self, "Missing URL", "Set the manager URL at the top of the window.")
            return

        self.refresh_button.setEnabled(False)
        self.status_label.setText("Loading...")

        async def task() -> tuple[dict[str, Any] | None, dict[str, Any] | None, str | None, str | None]:
            async with httpx.AsyncClient(timeout=30.0) as client:
                health, health_error = await fetch_health(client, manager_url)
                stats, stats_error = await fetch_stats(client, manager_url)
                return health, stats, health_error, stats_error

        self.worker = AsyncWorker(task, parent=self)
        self.worker.finished_ok.connect(self._on_loaded)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_loaded(self, payload: tuple) -> None:
        health, stats, health_error, stats_error = payload
        self.refresh_button.setEnabled(True)

        if health_error:
            self._clear_health(f"Health error: {health_error}")
        elif health:
            self._apply_health(health)

        if stats_error:
            self._clear_stats(f"Stats error: {stats_error}")
        elif stats:
            self._apply_stats(stats)

        if health_error and stats_error:
            self.status_label.setProperty("error", True)
            self.status_label.setText("Failed to load /health and /stats")
        elif health_error or stats_error:
            self.status_label.setProperty("warning", True)
            self.status_label.setText("Loaded with partial errors")
        else:
            self.status_label.setProperty("error", False)
            self.status_label.setProperty("warning", False)
            self.status_label.setText("Loaded /health and /stats")

        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _on_failed(self, error: str) -> None:
        self.refresh_button.setEnabled(True)
        self.status_label.setText("Load failed")
        QMessageBox.warning(self, "Overview load failed", error)

    def _apply_health(self, payload: dict[str, Any]) -> None:
        self.health_status.setText(str(payload.get("status", "—")))
        self.health_database.setText(str(payload.get("database", "—")))
        pool = payload.get("proxy_pool") or {}
        self._set_pool_labels(pool)

    def _clear_health(self, message: str) -> None:
        self.health_status.setText("—")
        self.health_database.setText("—")
        self._set_pool_labels({})
        self.status_label.setText(message)

    def _set_pool_labels(self, pool: dict[str, Any]) -> None:
        for key, label in self._pool_labels.items():
            value = pool.get(key)
            label.setText(str(value if value is not None else "—"))

    def _apply_stats(self, payload: dict[str, Any]) -> None:
        self.stats_total.setText(str(payload.get("total_proxies", "—")))
        self.stats_http.setText(str(payload.get("http", "—")))
        self.stats_https.setText(str(payload.get("https", "—")))

        avg_latency = payload.get("average_latency")
        self.stats_avg_latency.setText("—" if avg_latency is None else str(avg_latency))

        success_rate = payload.get("success_rate")
        self.stats_success_rate.setText("—" if success_rate is None else str(success_rate))

        countries = payload.get("proxies_by_country") or {}
        sorted_countries = sorted(countries.items(), key=lambda item: (-item[1], item[0]))
        self._fill_table(
            self.countries_table,
            [[code, str(count)] for code, count in sorted_countries],
        )

        sources = payload.get("sources") or []
        source_rows = []
        for source in sources:
            source_rows.append(
                [
                    str(source.get("name", "")),
                    str(source.get("enabled", "")),
                    str(source.get("proxies_found", "")),
                    str(source.get("valid_proxies", "")),
                    "—" if source.get("success_rate") is None else str(source.get("success_rate")),
                    iso_value(source.get("last_run")) or "—",
                    iso_value(source.get("last_success")) or "—",
                    str(source.get("last_error") or "—"),
                ]
            )
        self._fill_table(self.sources_table, source_rows)

    def _clear_stats(self, message: str) -> None:
        self.stats_total.setText("—")
        self.stats_http.setText("—")
        self.stats_https.setText("—")
        self.stats_avg_latency.setText("—")
        self.stats_success_rate.setText("—")
        self.countries_table.setRowCount(0)
        self.sources_table.setRowCount(0)
        if not self.status_label.text().startswith("Health error"):
            self.status_label.setText(message)

    @staticmethod
    def _fill_table(table: QTableWidget, rows: list[list[str]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        for row_index, values in enumerate(rows):
            for col_index, value in enumerate(values):
                cell = QTableWidgetItem(value)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                table.setItem(row_index, col_index, cell)
        table.resizeColumnsToContents()
        table.setSortingEnabled(True)
