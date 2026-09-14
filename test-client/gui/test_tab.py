from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from client_lib.models import DEFAULT_TARGET_URL, DEFAULT_TIMEOUT, LIST_PROXY_COUNT, PROXY_CALLS
from client_lib.runner import format_report, run_batch, serialize_results
from gui.workers import ProgressAsyncWorker


class TestTab(QWidget):
    def __init__(self, manager_url_getter, parent=None) -> None:
        super().__init__(parent)
        self.manager_url_getter = manager_url_getter
        self.worker: ProgressAsyncWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        params_box = QGroupBox("Test parameters")
        form = QFormLayout(params_box)

        self.target_url = QLineEdit(DEFAULT_TARGET_URL)
        self.timeout = QDoubleSpinBox()
        self.timeout.setRange(1.0, 120.0)
        self.timeout.setValue(DEFAULT_TIMEOUT)
        self.proxy_calls = QSpinBox()
        self.proxy_calls.setRange(1, 100)
        self.proxy_calls.setValue(PROXY_CALLS)
        self.list_count = QSpinBox()
        self.list_count.setRange(1, 100)
        self.list_count.setValue(LIST_PROXY_COUNT)
        self.list_protocol = QLineEdit("http")
        self.list_status = QLineEdit("HEALTHY")
        self.list_fetch_limit = QSpinBox()
        self.list_fetch_limit.setRange(1, 100)
        self.list_fetch_limit.setValue(100)
        self.list_anonymous = QCheckBox("Anonymous only (GET /proxies)")
        self.list_anonymous.setChecked(True)
        self.min_score = QDoubleSpinBox()
        self.min_score.setRange(0.0, 100.0)
        self.min_score.setSpecialValueText("(none)")
        self.min_score.setValue(0.0)
        self.min_score.setDecimals(1)
        self.concurrency = QSpinBox()
        self.concurrency.setRange(1, 50)
        self.concurrency.setValue(5)
        self.wait_seconds = QDoubleSpinBox()
        self.wait_seconds.setRange(0.0, 3600.0)
        self.wait_seconds.setValue(0.0)
        self.wait_poll_seconds = QDoubleSpinBox()
        self.wait_poll_seconds.setRange(1.0, 60.0)
        self.wait_poll_seconds.setValue(5.0)

        form.addRow("Target URL", self.target_url)
        form.addRow("Timeout (s)", self.timeout)
        form.addRow("GET /proxy calls", self.proxy_calls)
        form.addRow("List pick count", self.list_count)
        form.addRow("List protocol", self.list_protocol)
        form.addRow("List status", self.list_status)
        form.addRow("List fetch limit", self.list_fetch_limit)
        form.addRow("", self.list_anonymous)
        form.addRow("Min score (/proxy)", self.min_score)
        form.addRow("Concurrency", self.concurrency)
        form.addRow("Wait seconds", self.wait_seconds)
        form.addRow("Wait poll (s)", self.wait_poll_seconds)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(params_box)
        scroll.setMaximumHeight(280)
        root.addWidget(scroll)

        actions = QHBoxLayout()
        self.run_button = QPushButton("Run tests")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(self.run_tests)
        self.save_json_button = QPushButton("Save JSON report")
        self.save_json_button.setEnabled(False)
        self.save_json_button.clicked.connect(self.save_json_report)
        self.clear_button = QPushButton("Clear log")
        self.clear_button.clicked.connect(lambda: self.log.clear())
        actions.addWidget(self.run_button)
        actions.addWidget(self.save_json_button)
        actions.addWidget(self.clear_button)
        actions.addStretch()
        root.addLayout(actions)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QTextEdit.NoWrap)
        root.addWidget(self.log)

        self._last_report: dict[str, Any] | None = None

    def _min_score_value(self) -> float | None:
        value = self.min_score.value()
        return None if value <= 0 else value

    def run_tests(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        manager_url = self.manager_url_getter().strip()
        if not manager_url:
            QMessageBox.warning(self, "Missing URL", "Set the manager URL at the top of the window.")
            return

        self.run_button.setEnabled(False)
        self.save_json_button.setEnabled(False)
        self.log.clear()
        self.log.append(f"Manager: {manager_url}")
        self.log.append(f"Target:  {self.target_url.text().strip()}")
        self.log.append("Running batch...")

        kwargs = {
            "manager_url": manager_url,
            "target_url": self.target_url.text().strip(),
            "timeout": self.timeout.value(),
            "proxy_calls": self.proxy_calls.value(),
            "list_count": self.list_count.value(),
            "list_fetch_limit": self.list_fetch_limit.value(),
            "list_protocol": self.list_protocol.text().strip() or "http",
            "list_status": self.list_status.text().strip() or "HEALTHY",
            "list_anonymous": self.list_anonymous.isChecked(),
            "min_score": self._min_score_value(),
            "concurrency": self.concurrency.value(),
            "wait_seconds": self.wait_seconds.value(),
            "wait_poll_seconds": self.wait_poll_seconds.value(),
        }

        self.worker = ProgressAsyncWorker(run_batch, kwargs=kwargs, parent=self)
        self.worker.progress.connect(self._append_log)
        self.worker.finished_ok.connect(self._on_finished)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _append_log(self, message: str) -> None:
        self.log.append(message)

    def _on_finished(self, payload: tuple[Any, Any]) -> None:
        results, diagnostics = payload
        report_text = format_report(
            results,
            self.target_url.text().strip(),
            self.manager_url_getter().strip(),
            diagnostics,
        )
        self.log.append(report_text)
        self._last_report = {
            "manager_url": self.manager_url_getter().strip(),
            "target_url": self.target_url.text().strip(),
            "generated_at": datetime.now(UTC).isoformat(),
            "diagnostics": asdict(diagnostics),
            "results": serialize_results(results),
        }
        self.run_button.setEnabled(True)
        self.save_json_button.setEnabled(True)

    def _on_failed(self, error: str) -> None:
        self.log.append(f"\nERROR:\n{error}")
        self.run_button.setEnabled(True)
        QMessageBox.critical(self, "Test failed", error)

    def save_json_report(self) -> None:
        if not self._last_report:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save JSON report",
            "report.json",
            "JSON files (*.json)",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(self._last_report, handle, indent=2, ensure_ascii=False)
        self.log.append(f"JSON report saved to {path}")
