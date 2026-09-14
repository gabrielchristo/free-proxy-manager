#!/usr/bin/env python3
"""GUI entry point for free-proxy-manager test client."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication

from gui.main_window import MainWindow

_THEME_PATH = Path(__file__).resolve().parent / "gui" / "theme.qss"


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("free-proxy-manager test client")
    app.setStyle("Fusion")
    app.setStyleSheet(_THEME_PATH.read_text(encoding="utf-8"))

    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
