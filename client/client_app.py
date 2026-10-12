import os
import json
import dotenv
import sounddevice as sd
from vosk import Model, KaldiRecognizer
import gigachat
import requests
import socket

dotenv.load_dotenv()
GIGACHAT_CREDITNAILS = os.getenv("GIGACHAT_CREDITNAILS")

VOSK_MODEL_PATH = "vosk-model-small-ru-0.22"

DISCOVERY_PORT = 37020
DEFAULT_SERVER_PORT = 8000
DISCOVERY_TIMEOUT = 3

RULES = {
    "следующ": {"action": "next"},
    "дальше": {"action": "next"},
    "предыдущ": {"action": "previous"},
    "назад": {"action": "previous"},
    "пауза": {"action": "pause"},
    "стоп": {"action": "pause"},
    "продолжить": {"action": "resume"}
}

PROMPT = """
Преврати фразу в JSON, без пояснений. 

Допустимые action: 
next, previous, pause, resume, volume, seek, play.

Правила:
- volume: value 0-100. 
- seek: value в секундах(минус назад). 
- play: query -название как сказано.
- Если непонятно: {"action": "none"}.

Возвращай только JSON объект
Фраза пользователя: 
"""

class Server_autodetection:
    def __init__(self, port=DEFAULT_SERVER_PORT, discovery_port=DISCOVERY_PORT, timeout=DISCOVERY_TIMEOUT):
        self.port = port
        self.discovery_port = discovery_port
        self.timeout = timeout

    def discover_server(self):

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        message = b"DISCOVER_SERVER"
        sock.sendto(message, ('<broadcast>', self.discovery_port))

        while True:
            try:
                data, addr = sock.recvfrom(1024)
                if data == b"SERVER_RESPONSE":
                    return addr[0], self.port
            except socket.timeout:
                break

        return None, None
