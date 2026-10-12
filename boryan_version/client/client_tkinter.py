import tkinter as tk
from tkinter import ttk
import requests
import threading
import queue
import json
import sys
from pathlib import Path

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
CONFIG_PATH = BASE / "config.json"

DEFAULTS = {"host": "127.0.0.1", "port": 8000}


def load_config():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULTS, indent=2, ensure_ascii=False), encoding="utf-8")
        return dict(DEFAULTS)
    try:
        return {**DEFAULTS, **json.loads(CONFIG_PATH.read_text(encoding="utf-8"))}
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULTS)

cfg = load_config()
BASE_URL = f"http://{cfg['host']}:{cfg['port']}"
SERVER_URL = f"{BASE_URL}/switch"
PING_URL = f"{BASE_URL}/ping"

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.geometry("250x200")
        self.title("Client_app")

        self.connection_status = ttk.Label(self, text = "Не проверено")
        self.connection_status.pack(side = tk.TOP)

        self.btn_sndrqst = ttk.Button(self, text="Press", command=self.send_request)
        self.btn_sndrqst.pack(expand=True, ipadx=15, ipady=15)

        self.btn_check = ttk.Button(self, text="check connection", 
                                    command=self.check_connection)
        self.btn_check.pack(side = tk.BOTTOM)

        self.tasks = queue.Queue()
        threading.Thread(target=self._sender, daemon=True).start()


    #------------проверка связи------------

    def check_connection(self):
        self.connection_status["text"] = "Попытка подключения..."
        self.btn_check["state"] = "disabled"
        threading.Thread(target=self._check_thread, daemon=True).start()

    def _check_thread(self):
        try:
            requests.get(PING_URL, timeout=3).raise_for_status()
            text = "Успешно подключено"
        except requests.RequestException:
            text = "Ошибка подключения"
        self.after(0,self._show_status, text)

    def _show_status(self, text):
        self.connection_status["text"] = text
        self.btn_check["state"] = "normal"

    #------------отправка запроса------------

    def send_request(self):
        self.tasks.put(1)

    def _sender(self):
        while True:
            self.tasks.get()        
            try:
                requests.get(SERVER_URL, timeout=2)
            except requests.RequestException:
                pass


if __name__ == '__main__':
    App().mainloop()