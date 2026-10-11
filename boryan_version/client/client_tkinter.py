import tkinter as tk
from tkinter import ttk
import requests
import threading
import queue

SERVER_URL = "http://127.0.0.1:8000/switch" #Адресс сервера
PING_URL = "http://127.0.0.1:8000/ping"
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