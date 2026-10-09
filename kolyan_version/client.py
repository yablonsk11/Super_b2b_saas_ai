import socket
from PyQt6.QtWidgets import QApplication, QMainWindow, QPushButton, QVBoxLayout, QWidget

TARGET_IP = "192.168.1.50"
TARGET_PORT = 5005


class ClientApp(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("client")
        self.resize(300, 150)

        self.button = QPushButton("change the image", self)
        self.button.clicked.connect(self.send_signal)

        layout = QVBoxLayout()
        layout.addWidget(self.button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

        # init udp socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def send_signal(self):
        try:
            self.sock.sendto(b"change", (TARGET_IP, TARGET_PORT))
            print(f"signal successfuly sent {TARGET_IP}:{TARGET_PORT}")
        except Exception as e:
            print(f"sending error: {e}")


if __name__ == "__main__":
    app = QApplication([])
    window = ClientApp()
    window.show()
    sys.exit(app.exec())
