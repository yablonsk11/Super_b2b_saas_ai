import queue
import threading
import tkinter as tk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image, ImageTk

HOST, PORT = "0.0.0.0", 8000         
IMAGES_DIR = Path(__file__).parent / "images" #Название папки с картинками
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