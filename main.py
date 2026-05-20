import sys
from PyQt6.QtWidgets import QApplication
from controllers.app_controller import AppController
from ui.styles import GLOBAL_STYLE

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_STYLE)
    controller = AppController()
    sys.exit(app.exec())