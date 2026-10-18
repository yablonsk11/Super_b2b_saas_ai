import json
from http.server import BaseHTTPRequestHandler

from server_spotify import SpotifyController, SpotifyError


class CommandHandler(BaseHTTPRequestHandler):
    controller: SpotifyController = None   # устанавливается из server_app

    def do_POST(self):
        if self.path != "/command":
            self._send_json(404, {"error": "Not found"})
            return

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            command = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return

        action = command.get("action")
        if not action or action == "none":
            self._send_json(400, {"error": "Invalid action"})
            return

        try:
            result = self.controller.execute(command)
            self._send_json(200, {"status": "ok", "result": result})
        except SpotifyError as e:
            self._send_json(500, {"error": str(e)})
        except Exception as e:
            self._send_json(500, {"error": f"Internal error: {e}"})

    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass
