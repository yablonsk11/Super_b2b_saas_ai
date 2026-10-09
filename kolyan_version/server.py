import socket
import sys
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow, QVBoxLayout, QWidget

LISTEN_PORT = 5005


class NetworkListener(QThread):
    signal_received = pyqtSignal()

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # listen all ports
        sock.bind(("0.0.0.0", LISTEN_PORT))

        while True:
            data, addr = sock.recvfrom(1024)
            if data == b"change":
                self.signal_received.emit()


class ClientApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("server")
        self.resize(500, 400)

        self.images = ["image1.png", "image2.png"]
        self.current_index = 0

        self.image_label = QLabel(self)
        self.image_label.setScaledContents(True)
        self.update_image()

        layout = QVBoxLayout()
        layout.addWidget(self.image_label)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        self.listener = NetworkListener()
        self.listener.signal_received.connect(self.change_image)
        self.listener.start()

    def update_image(self):
        pixmap = QPixmap(self.images[self.current_index])
        if not pixmap.isNull():
            self.image_label.setPixmap(pixmap)
        else:
            self.image_label.setText(
				f"could not load: {self.images[self.current_index]}"
				)

    def change_image(self):
        self.current_index = (self.current_index + 1) % len(self.images)
        self.update_image()
        print("the image has been successfuly changed based on a signal")


if __name__ == "__main__":
    app = QApplication([])
    window = ServerApp()
    window.show()
    sys.exit(app.exec())
 
