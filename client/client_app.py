
import sys

from PyQt6.QtWidgets import QApplication

import client_interface



if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = client_interface.JarvisWindow()
    window.show()
    sys.exit(app.exec())