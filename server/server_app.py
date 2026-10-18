import sys

from PyQt6.QtWidgets import QApplication

import server_interface


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = server_interface.ServerWindow()
    window.show()
    sys.exit(app.exec())
