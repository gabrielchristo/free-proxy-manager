from __future__ import annotations

from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from client_lib.models import DEFAULT_MANAGER_URL
from gui.history_tab import HistoryTab
from gui.overview_tab import OverviewTab
from gui.proxies_tab import ProxiesTab
from gui.test_tab import TestTab


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("free-proxy-manager test client")
        self.resize(1200, 800)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        url_row = QHBoxLayout()
        url_bar = QWidget()
        url_bar.setObjectName("managerUrlBar")
        url_row_inner = QHBoxLayout(url_bar)
        url_row_inner.setContentsMargins(0, 0, 0, 0)
        url_row_inner.addWidget(QLabel("Manager URL"))
        self.manager_url = QLineEdit(DEFAULT_MANAGER_URL)
        self.manager_url.setPlaceholderText("http://localhost:9321")
        url_row_inner.addWidget(self.manager_url, stretch=1)
        url_row.addWidget(url_bar)
        layout.addLayout(url_row)

        self.tabs = QTabWidget()
        self.test_tab = TestTab(self.get_manager_url)
        self.overview_tab = OverviewTab(self.get_manager_url)
        self.proxies_tab = ProxiesTab(self.get_manager_url)
        self.history_tab = HistoryTab(self.get_manager_url)
        self.tabs.addTab(self.test_tab, "Integration tests")
        self.tabs.addTab(self.overview_tab, "Overview")
        self.tabs.addTab(self.proxies_tab, "Proxy database")
        self.tabs.addTab(self.history_tab, "Pool history")
        layout.addWidget(self.tabs)

    def get_manager_url(self) -> str:
        return self.manager_url.text().strip()
