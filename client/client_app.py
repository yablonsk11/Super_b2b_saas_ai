import os
import json
import dotenv
import sounddevice as sd
from vosk import Model, KaldiRecognizer, SetLogLevel
import gigachat
import requests
import socket
import time 
import queue
import threading
import traceback
import difflib

dotenv.load_dotenv()
GIGACHAT_CREDITNAILS = os.getenv("GIGACHAT_CREDITNAILS")
MAX_RULE_WORDS = 3          # правила только для коротких фраз

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

class VoiceListener:
    """Слушает микрофон постоянно, но передаёт дальше только то, что сказано
    после слова активации ("джарвис")."""

    def __init__(self, model_path=VOSK_MODEL_PATH,
                 wake_words=("джарвис", "джарвиз", "жарвис"),
                 on_wake=None, on_command=None,
                 command_timeout=6.0, samplerate=16000,
                 wake_threshold=0.75):
        SetLogLevel(-1)
        self.model = Model(model_path)
        self.wake_words = [w.lower() for w in wake_words]
        self.on_wake = on_wake or (lambda: None)
        self.on_command = on_command or (lambda text: None)
        self.command_timeout = command_timeout
        self.samplerate = samplerate
        self.wake_threshold = wake_threshold

        self._audio = queue.Queue()
        self._stop = threading.Event()
        self._thread = None

    # ---------- микрофон ----------

    @staticmethod
    def find_input_device(prefer=("pipewire", "pulse")):
        """Номер входного устройства по имени. Битые имена пропускаются."""
        for name in prefer:
            for i in range(64):
                try:
                    d = sd.query_devices(i)
                except UnicodeDecodeError:
                    continue
                except sd.PortAudioError:
                    break
                if d["max_input_channels"] > 0 and d["name"] == name:
                    return i
        return None

    # ---------- управление ----------

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run_safe, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    # ---------- разбор фразы ----------

    def _is_wake(self, word):
        """Слово похоже на слово активации (Vosk пишет и 'жарвис', и 'джарвиз')."""
        return any(
            difflib.SequenceMatcher(None, word, w).ratio() >= self.wake_threshold
            for w in self.wake_words
        )

    def _extract_command(self, text):
        """Текст после слова активации.
        '' - сказано только слово активации, None - его в фразе нет."""
        words = text.split()
        for i, w in enumerate(words):
            if self._is_wake(w):
                return " ".join(words[i + 1:])
        return None

    # ---------- внутренности ----------

    def _callback(self, indata, frames, time_info, status):
        self._audio.put(bytes(indata))

    def _run_safe(self):
        try:
            self._run()
        except Exception:
            traceback.print_exc()          # ошибки потока не теряются

    def _run(self):
        rec = KaldiRecognizer(self.model, self.samplerate)
        armed_until = 0.0                  # окно после одиноко сказанного "джарвис"

        with sd.RawInputStream(samplerate=self.samplerate, blocksize=4000,
                               dtype="int16", channels=1,
                               device=self.find_input_device(),
                               callback=self._callback):
            while not self._stop.is_set():
                try:
                    data = self._audio.get(timeout=0.2)
                except queue.Empty:
                    continue

                if not rec.AcceptWaveform(data):
                    continue               # фраза ещё не закончилась

                text = json.loads(rec.Result()).get("text", "").strip()
                if not text:
                    continue

                cmd = self._extract_command(text)

                if cmd is None:
                    # слова активации нет: берём фразу, только если оно прозвучало
                    # отдельно за последние command_timeout секунд
                    if time.monotonic() < armed_until:
                        armed_until = 0.0
                        self.on_command(text)
                elif cmd == "":
                    # сказали только "джарвис": ждём команду следующей фразой
                    armed_until = time.monotonic() + self.command_timeout
                    self.on_wake()
                else:
                    armed_until = 0.0
                    self.on_command(cmd)

# ---------- обработка текста ----------
class CommandProcessor:
    def __init__(self, rules=RULES, prompt=PROMPT):
        self.rules = rules
        self.prompt = prompt
        self.client = gigachat.GigaChat(
            credentials=GIGACHAT_CREDITNAILS,
            base_url="https://api.giga.chat/v1",
            scope="GIGACHAT_API_PERS",
            model="GigaChat-2",
            verify_ssl_certs=False,
        )

    def process(self, text):
        """Возвращает словарь с командой и параметрами."""
        text = text.lower().strip()

        # 1. быстрые правила: только для коротких фраз
        if len(text.split()) <= MAX_RULE_WORDS:
            for key, value in self.rules.items():
                if key in text:
                    return value

        # 2. сложные фразы отдаём GigaChat
        try:
            response = self.client.chat.create(self.prompt + text)
            answer = response.messages[0].content[0].text
        except Exception as e:
            print("Ошибка GigaChat:", e)
            return {"action": "none"}

        return self._parse(answer)

    @staticmethod
    def _parse(answer):
        """Достаёт JSON, даже если модель обернула его в ```json ... ```."""
        answer = answer.strip().strip("`").removeprefix("json").strip()
        try:
            data = json.loads(answer)
        except json.JSONDecodeError:
            return {"action": "none"}
        return data if isinstance(data, dict) else {"action": "none"}
processor = CommandProcessor()

def handle_command(text):
    print("Услышал:", text)
    result = processor.process(text)
    print("Разобрано:", result)

listener = VoiceListener(
    on_wake=lambda: print("Слушаю..."),
    on_command=handle_command,
)
listener.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    listener.stop()