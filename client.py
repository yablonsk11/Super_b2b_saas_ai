import sys
from PyQt6.QtNetwork import QUdpSocket, QHostAddress
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton

# window configiration
WINDOW_TITLE = "client"
WIDTH = 300
HEIGHT = 150

# interface
BUTTON_TEXT = "change the image"

# network
TARGET_IP = "127.0.0.1"
TARGET_PORT = 5005
DATAGRAM_PAYLOAD = b"change"
ERROR_CODE = -1

# logging
LOG_SUCCESS = f"signal successfuly sent {TARGET_IP}:{TARGET_PORT}"
LOG_ERROR = "sending error"


class ClientApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(WINDOW_TITLE)
        self.resize(WIDTH, HEIGHT)

        btn = QPushButton(BUTTON_TEXT, self)
        btn.clicked.connect(self.send_signal)
        self.setCentralWidget(btn)

        self.sock = QUdpSocket(self)

    def send_signal(self):
        status = self.sock.writeDatagram(DATAGRAM_PAYLOAD, QHostAddress(TARGET_IP), TARGET_PORT)
        
        if status != ERROR_CODE:
            print(LOG_SUCCESS)
        else:
            print(LOG_ERROR)


if __name__ == "__main__":
    app = QApplication([])
    window = ClientApp()
    window.show()
    sys.exit(app.exec())
