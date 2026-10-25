import socket
import threading
from http.server import ThreadingHTTPServer

from server_config import DEFAULT_SERVER_PORT
from server_discovery import DiscoveryResponder
from server_http import CommandHandler
from server_spotify import SpotifyController, SpotifyError


def get_local_ip() -> str:
    """IP-адрес, по которому клиент в локальной сети увидит сервер."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except OSError:
        return "127.0.0.1"


class ServerController:
    """Управляет запуском и остановкой HTTP-сервера и UDP-discovery."""

    def __init__(self, on_log=None, on_event=None, on_error=None, on_command_start=None):
        self.on_log = on_log or (lambda msg, color: None)
        self.on_event = on_event or (lambda cmd, ok, msg: None)
        self.on_error = on_error or (lambda msg: None)
        self.on_command_start = on_command_start or (lambda cmd: None)

        self.spotify = None
        self.http_server = None
        self.http_thread = None
        self.discovery = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def address(self) -> str:
        return f"http://{get_local_ip()}:{DEFAULT_SERVER_PORT}"

    def start(self):
        if self._running:
            return

        # 1. Авторизация в Spotify (может бросить SpotifyError)
        try:
            self.spotify = SpotifyController()
            self.spotify.check()
        except SpotifyError as e:
            self.on_error(f"Spotify: {e}")
            self.spotify = None
            raise

        # 2. HTTP-сервер
        CommandHandler.controller = self.spotify
        CommandHandler.on_event = self.on_event
        CommandHandler.on_command_start = self.on_command_start

        try:
            self.http_server = ThreadingHTTPServer(
                ("0.0.0.0", DEFAULT_SERVER_PORT), CommandHandler
            )
        except OSError as e:
            self.on_error(f"Не удалось занять порт {DEFAULT_SERVER_PORT}: {e}")
            self.http_server = None
            raise

        self.http_thread = threading.Thread(
            target=self.http_server.serve_forever, daemon=True
        )
        self.http_thread.start()

        # 3. UDP-discovery
        self.discovery = DiscoveryResponder()
        self.discovery.start()

        self._running = True

    def stop(self):
        if not self._running:
            return
        self._running = False

        if self.discovery:
            self.discovery.stop()
            self.discovery = None

        if self.http_server:
            self.http_server.shutdown()
            self.http_server.server_close()
            self.http_server = None

        if self.http_thread:
            self.http_thread.join(timeout=2)
            self.http_thread = None

        CommandHandler.controller = None
        CommandHandler.on_event = None
        CommandHandler.on_command_start = None
