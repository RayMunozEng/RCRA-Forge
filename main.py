"""
RCRA Forge - Ratchet & Clank: Rift Apart Level Editor & Asset Exporter
Entry point
"""

import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtCore import QSharedMemory
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from ui.main_window import MainWindow


def main():
    game_folder = sys.argv[1] if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]) else None
    app = QApplication([sys.argv[0]])
    app.setApplicationName("RCRA Forge")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("RCRA Community")
    # HiDPI is always enabled in PyQt6 6.0+ — no setAttribute needed

    # Let the application, rather than an OS process query in the launcher,
    # own the single-instance guarantee.  The shared-memory segment is removed
    # automatically when the owning process exits, including after a crash.
    instance_guard = QSharedMemory("rcra-forge-desktop-single-instance")
    if not instance_guard.create(1):
        if instance_guard.error() == QSharedMemory.SharedMemoryError.AlreadyExists:
            return 0
        print(
            f"Could not create the RCRA Forge instance guard: {instance_guard.errorString()}",
            file=sys.stderr,
        )
        return 1

    window = MainWindow()
    window.show()
    if game_folder:
        window.load_game_folder(game_folder)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
