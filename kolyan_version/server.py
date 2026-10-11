import sys
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtNetwork import QUdpSocket, QHostAddress
from PyQt6.QtWidgets import QApplication, QLabel, QMainWindow

# image settings
IMAGE_FOLDER = "images/"
ROW_IMAGES = ["hamster.jpg", "kolobok.jpg"]
IMAGES = [IMAGE_FOLDER + img for img in ROW_IMAGES]
START_INDEX = 0

# window configuration
WINDOW_TITLE = "server"
WIDTH = 1280
HEIGHT = 720

# network
BIND_ADDRESS = QHostAddress.SpecialAddress.Any
LISTEN_PORT = 5005
EXPECTED_PAYLOAD = b"change"

# logging
LOG_SUCCESS = "the image has been successfuly changed based on a signal"

# error
ERROR_LOAD_TEXT = "could not load: "


class ServerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WIDTH, HEIGHT)
        self.idx = START_INDEX

        self.lbl = QLabel(self)
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCentralWidget(self.lbl)

        self.sock = QUdpSocket(self)
        self.sock.bind(BIND_ADDRESS, LISTEN_PORT)
        self.sock.readyRead.connect(self.read_data)
        self.update_img()

    def read_data(self):
        while self.sock.hasPendingDatagrams():
            datagram, _, _ = self.sock.readDatagram(self.sock.pendingDatagramSize())
            if datagram == EXPECTED_PAYLOAD:
                self.idx = (self.idx + 1) % len(IMAGES)
                self.update_img()
                print(LOG_SUCCESS)

    def update_img(self):
        pix = QPixmap(IMAGES[self.idx])
        if not pix.isNull():
            scaled_pix = pix.scaled(
                self.lbl.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            self.lbl.setPixmap(scaled_pix)
        else:
            self.lbl.setText(f"{ERROR_LOAD_TEXT}{IMAGES[self.idx]}")

    def resizeEvent(self, event):
        self.update_img()


if __name__ == "__main__":
    app = QApplication([])
    window = ServerApp()
    window.show()
    sys.exit(app.exec())
