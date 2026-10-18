import socket
import threading

from server_config import DISCOVERY_PORT, DISCOVERY_REQUEST, DISCOVERY_RESPONSE


class DiscoveryResponder(threading.Thread):
    def __init__(self, port=DISCOVERY_PORT):
        super().__init__(daemon=True)
        self.port = port
        self._stop_event = threading.Event()

    def run(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", self.port))
        sock.settimeout(1.0)
        print(f"[Discovery] Слушаю UDP :{self.port}")
        try:
            while not self._stop_event.is_set():
                try:
                    data, addr = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                if data == DISCOVERY_REQUEST:
                    sock.sendto(DISCOVERY_RESPONSE, addr)
                    print(f"[Discovery] Ответил {addr}")
        finally:
            sock.close()

    def stop(self):
        self._stop_event.set()
