import threading
from http.server import ThreadingHTTPServer

from server_config import DEFAULT_SERVER_PORT
from server_http import CommandHandler
from server_spotify import SpotifyController
from server_discovery import DiscoveryResponder


def main():
    controller = SpotifyController()
    CommandHandler.controller = controller

    http_server = ThreadingHTTPServer(("0.0.0.0", DEFAULT_SERVER_PORT), CommandHandler)
    http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
    http_thread.start()
    print(f"[HTTP] Сервер слушает :{DEFAULT_SERVER_PORT}")

    discovery = DiscoveryResponder()
    discovery.start()

    try:
        http_thread.join()
    except KeyboardInterrupt:
        print("\n[Server] Остановка…")
    finally:
        discovery.stop()
        http_server.shutdown()
        http_server.server_close()


if __name__ == "__main__":
    main()
