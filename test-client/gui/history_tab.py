from __future__ import annotations

import httpx
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.dates import DateFormatter
from matplotlib.figure import Figure
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from client_lib.api import fetch_pool_history
from client_lib.models import (
    HISTORY_AUTO_REFRESH_SECONDS,
    HISTORY_MONTH_HOURS,
    HISTORY_MONTH_MAX_POINTS,
    PoolHistoryPoint,
)
from gui.workers import AsyncWorker

SERIES = {
    "total_proxies": ("Total proxies", "#7b8499"),
    "healthy": ("Healthy", "#2f9e44"),
    "degraded": ("Degraded", "#c68400"),
    "dead": ("Dead", "#d64545"),
    "new": ("New", "#3b6fd8"),
    "checking": ("Checking", "#7c5cbf"),
    "disabled": ("Disabled", "#9aa3b8"),
    "in_cooldown": ("In cooldown", "#0e8a9a"),
}


class HistoryTab(QWidget):
    def __init__(self, manager_url_getter, parent=None) -> None:
        super().__init__(parent)
        self.manager_url_getter = manager_url_getter
        self.worker: AsyncWorker | None = None
        self.points: list[PoolHistoryPoint] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        params = QGroupBox("Chart parameters")
        form = QFormLayout(params)

        self.hours = QSpinBox()
        self.hours.setRange(1, HISTORY_MONTH_HOURS)
        self.hours.setValue(HISTORY_MONTH_HOURS)
        self.limit = QSpinBox()
        self.limit.setRange(10, HISTORY_MONTH_MAX_POINTS)
        self.limit.setValue(HISTORY_MONTH_MAX_POINTS)
        self.auto_refresh = QCheckBox("Auto refresh")
        self.refresh_seconds = QSpinBox()
        self.refresh_seconds.setRange(10, 3600)
        self.refresh_seconds.setValue(HISTORY_AUTO_REFRESH_SECONDS)

        form.addRow("Hours", self.hours)
        form.addRow("Max points", self.limit)
        form.addRow("", self.auto_refresh)
        form.addRow("Refresh interval (s)", self.refresh_seconds)

        root.addWidget(params)

        series_box = QGroupBox("Series")
        series_layout = QGridLayout(series_box)
        self.series_checks: dict[str, QCheckBox] = {}
        defaults = {"healthy", "degraded", "dead", "in_cooldown", "total_proxies"}
        for index, (key, (label, _color)) in enumerate(SERIES.items()):
            checkbox = QCheckBox(label)
            checkbox.setChecked(key in defaults)
            self.series_checks[key] = checkbox
            row, col = divmod(index, 4)
            series_layout.addWidget(checkbox, row, col)
        root.addWidget(series_box)

        actions = QHBoxLayout()
        self.refresh_button = QPushButton("Refresh chart")
        self.refresh_button.setObjectName("primaryButton")
        self.refresh_button.clicked.connect(self.refresh_chart)
        self.status_label = QLabel("No data loaded")
        self.status_label.setObjectName("statusLabel")
        actions.addWidget(self.refresh_button)
        actions.addWidget(self.status_label, stretch=1)
        root.addLayout(actions)

        self.figure = Figure(figsize=(8, 4), tight_layout=True, facecolor="#ffffff")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setObjectName("chartCanvas")
        root.addWidget(self.canvas)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_chart)

        self.auto_refresh.toggled.connect(self._toggle_auto_refresh)
        self.refresh_seconds.valueChanged.connect(self._reset_timer_interval)

    def _toggle_auto_refresh(self, enabled: bool) -> None:
        if enabled:
            self._reset_timer_interval()
            self.timer.start()
        else:
            self.timer.stop()

    def _reset_timer_interval(self) -> None:
        if self.auto_refresh.isChecked():
            self.timer.setInterval(self.refresh_seconds.value() * 1000)

    def refresh_chart(self) -> None:
        if self.worker and self.worker.isRunning():
            return

        manager_url = self.manager_url_getter().strip()
        if not manager_url:
            QMessageBox.warning(self, "Missing URL", "Set the manager URL at the top of the window.")
            return

        self.refresh_button.setEnabled(False)
        self.status_label.setText("Loading history...")

        hours = self.hours.value()
        limit = self.limit.value()

        async def task() -> list[PoolHistoryPoint]:
            async with httpx.AsyncClient(timeout=30.0) as client:
                points, error = await fetch_pool_history(
                    client,
                    manager_url,
                    hours=hours,
                    limit=limit,
                )
                if error:
                    raise RuntimeError(error)
                return points

        self.worker = AsyncWorker(task, parent=self)
        self.worker.finished_ok.connect(self._on_loaded)
        self.worker.failed.connect(self._on_failed)
        self.worker.start()

    def _on_loaded(self, points: list[PoolHistoryPoint]) -> None:
        self.points = points
        self._draw_chart()
        self.refresh_button.setEnabled(True)
        if points:
            first = points[0].recorded_at.strftime("%Y-%m-%d %H:%M")
            last = points[-1].recorded_at.strftime("%Y-%m-%d %H:%M")
            self.status_label.setText(f"{len(points)} points | {first} → {last}")
        else:
            self.status_label.setText("No snapshots yet (enable STATS_SNAPSHOT_INTERVAL on the server)")

    def _on_failed(self, error: str) -> None:
        self.refresh_button.setEnabled(True)
        self.status_label.setProperty("error", True)
        self.status_label.setText("Load failed")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        QMessageBox.warning(self, "History load failed", error)

    def _draw_chart(self) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111, facecolor="#fafbfd")
        ax.tick_params(colors="#4b5168", labelsize=9)
        for spine in ax.spines.values():
            spine.set_color("#d8dce8")

        if not self.points:
            ax.text(
                0.5,
                0.5,
                "No data",
                ha="center",
                va="center",
                transform=ax.transAxes,
                color="#9aa3b8",
            )
            self.canvas.draw()
            return

        times = [point.recorded_at for point in self.points]
        for key, (_label, color) in SERIES.items():
            checkbox = self.series_checks[key]
            if not checkbox.isChecked():
                continue
            values = [getattr(point, key) for point in self.points]
            ax.plot(times, values, label=checkbox.text(), color=color, linewidth=1.8)

        ax.set_title("Proxy pool history", color="#1e2030", fontsize=12, pad=12)
        ax.set_xlabel("Time", color="#4b5168")
        ax.set_ylabel("Count", color="#4b5168")
        ax.grid(True, alpha=0.35, color="#d8dce8")
        legend = ax.legend(loc="upper left", fontsize=8, framealpha=0.95)
        legend.get_frame().set_facecolor("#ffffff")
        legend.get_frame().set_edgecolor("#d8dce8")
        for text in legend.get_texts():
            text.set_color("#1e2030")
        ax.xaxis.set_major_formatter(DateFormatter("%m-%d %H:%M"))
        self.figure.autofmt_xdate(rotation=30)
        self.canvas.draw()
