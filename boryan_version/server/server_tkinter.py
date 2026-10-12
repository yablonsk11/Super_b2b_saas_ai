import queue
import threading
import tkinter as tk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image, ImageTk
import json
import sys

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = BASE / "config.json"


def load_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULTS, indent=2, ensure_ascii=False), encoding="utf-8")
        return dict(DEFAULTS)
    try:
        return {**DEFAULTS, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)

DEFAULTS = {"host": "0.0.0.0", "port": 8000, "images_dir": "images"}

cfg = load_config()
HOST, PORT = cfg["host"], cfg["port"]

images = Path(cfg["images_dir"])
IMAGES_DIR = images if images.is_absolute() else BASE / images

EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp"} #Поддерживаемые расширения файлов

events = queue.Queue()                 

#----------Обработка запросов----------

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/switch"):
            events.put("switch")
            self._reply(200, "switched")
        elif self.path.startswith("/ping"):
            self._reply(200, "pong")
        else:
            self._reply(404, "not found")

    def _reply(self, code, text):
        body = text.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):      
        pass

#----------Приложение----------

class Viewer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Server_app")
        self.geometry("800x600")

        self.paths = sorted(
            p for p in IMAGES_DIR.glob("*") if p.suffix.lower() in EXTENSIONS
        )
        self.index = 0
        self.photo = None             

        self.label = tk.Label(self, bg="black", fg="white")
        self.label.pack(fill="both", expand=True)

        self.update_idletasks()
        self.show()
        self.after(20, self.poll)

    def show(self):
        if not self.paths:
            self.label.config(text=f"Положи картинки в папку:\n{IMAGES_DIR}")
            return
        img = Image.open(self.paths[self.index])
        img.thumbnail((self.winfo_width(), self.winfo_height()))
        self.photo = ImageTk.PhotoImage(img)
        self.label.config(image=self.photo)

    def poll(self):                    
        changed = False
        while not events.empty():
            events.get()
            if self.paths:
                self.index = (self.index + 1) % len(self.paths)
                changed = True
        if changed:
            self.show()                
        self.after(20, self.poll)


if __name__ == "__main__":
    IMAGES_DIR.mkdir(exist_ok=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    Viewer().mainloop()