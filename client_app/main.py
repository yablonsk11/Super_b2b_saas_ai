from tkinter import *
from tkinter import ttk
import requests

SERVER_URL = "http://192.168.1.50:8000/api/endpoint"
#IP-адресс сервера

def check_connection():
    try:
        r = requests.get(SERVER_URL, timeout=3)
        connection_status["text"] = "Успешно подключено"
    except requests.RequestException:
        connection_status["text"] = "Пососал"

def finish():
    root.destroy()  # ручное закрытие окна и всего приложения

def send_request(): #отправление запроса по нажатию кнопки
    # payload = {'key1':'value1', 'key2':'value2'}
    # r = requests.get(SERVER_URL,params=payload, timeout = 5)
    pass

root = Tk()
root.geometry("250x200") # размер окна

root.title("Client_app") #Название окна
root.protocol("WM_DELETE_WINDOW", finish)

btn_sndrqst = ttk.Button(text="Press", command=send_request)
btn_sndrqst.pack(expand=True, ipadx=15, ipady=15)

btn_check = ttk.Button(text="check connection", command=check_connection)
btn_check.pack(side=BOTTOM)

connection_status = ttk.Label()
connection_status.pack(side=TOP)


root.mainloop()