import socket
import queue
import threading
import requests


from config import DEFAULT_SERVER_PORT, DISCOVERY_PORT, DISCOVERY_TIMEOUT


class Server_autodetection:
    def __init__(self, port=DEFAULT_SERVER_PORT, discovery_port=DISCOVERY_PORT,
                 timeout=DISCOVERY_TIMEOUT):
        self.port = port
        self.discovery_port = discovery_port
        self.timeout = timeout

    def discover_server(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.sendto(b"DISCOVER_SERVER", ('<broadcast>', self.discovery_port))
            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                except socket.timeout:
                    break
                if data == b"SERVER_RESPONSE":
                    return addr[0], self.port
        except OSError:
            pass
        finally:
            sock.close()
        return None, None

class RequestSender:
    def __init__(self, on_error=None, on_result=None):
        self.detection = Server_autodetection()
        self.base_url = None
        self.on_error = on_error or (lambda msg: print("Ошибка:", msg))
        self.on_result = on_result or (lambda cmd, status: None)

        self._tasks = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    # ---------- публичное ----------

    def connect(self):
        """Ищет сервер в сети. True, если нашёл (блокирует до таймаута)."""
        return self._find_server()

    def send(self, command):
        if command and command.get("action") != "none":
            self._tasks.put(command)

    def stop(self):
        self._tasks.put(None)

    # ---------- внутренности ----------

    def _find_server(self):
        host, port = self.detection.discover_server()
        if host is None:
            return False
        self.base_url = f"http://{host}:{port}"
        return True

    def _worker(self):
        session = requests.Session()
        while True:
            command = self._tasks.get()
            if command is None:
                break

            if self.base_url is None and not self._find_server():
                self.on_error("Сервер не найден в сети")
                continue

            try:
                r = session.post(f"{self.base_url}/command", json=command, timeout=3)
                self.on_result(command, r.status_code)
                if r.status_code >= 400:
                    self.on_error(f"Сервер ответил {r.status_code}: {r.text}")
            except requests.RequestException as e:
                self.base_url = None
                self.on_error(f"Нет связи с сервером ({e.__class__.__name__})")

        session.close()

