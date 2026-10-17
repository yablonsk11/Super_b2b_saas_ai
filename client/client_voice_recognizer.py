import queue
import gigachat
import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel
import threading
from array import array
import difflib
import traceback
import time
import sounddevice as sd
import json

from config import VOSK_MODEL_PATH, RULES, PROMPT, GIGACHAT_CREDITNAILS, MAX_RULE_WORDS


class VoiceListener:

    def __init__(self, model_path=VOSK_MODEL_PATH,
                 wake_words=("джарвис", "джарвиз", "жарвис"),
                 on_wake=None, on_idle=None, on_command=None,
                 on_level=None, on_error=None,
                 command_timeout=6.0, samplerate=16000,
                 wake_threshold=0.75):
        SetLogLevel(-1)
        self.model = Model(model_path)
        self.wake_words = [w.lower() for w in wake_words]
        self.on_wake = on_wake or (lambda: None)
        self.on_idle = on_idle or (lambda: None)
        self.on_command = on_command or (lambda text: None)
        self.on_level = on_level or (lambda x: None)
        self.on_error = on_error or (lambda msg: None)
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
        data = bytes(indata)
        self._audio.put(data)
        samples = array("h", data)
        if samples:
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
            self.on_level(min(1.0, rms / 4000))

    def _run_safe(self):
        try:
            self._run()
        except Exception as e:
            traceback.print_exc()
            self.on_error(f"Ошибка микрофона: {e}")

    def _run(self):
        rec = KaldiRecognizer(self.model, self.samplerate)
        armed_until = 0.0      # окно ожидания после одиноко сказанного "джарвис"
        awake = False          # слово активации уже услышано в этой фразе

        with sd.RawInputStream(samplerate=self.samplerate, blocksize=1600,
                               dtype="int16", channels=1,
                               device=self.find_input_device(),
                               callback=self._callback):
            while not self._stop.is_set():
                try:
                    data = self._audio.get(timeout=0.2)
                except queue.Empty:
                    continue

                # вышло время ожидания команды
                if armed_until and time.monotonic() > armed_until:
                    armed_until = 0.0
                    awake = False
                    self.on_idle()

                if not rec.AcceptWaveform(data):
                    # фраза ещё идёт: ловим слово активации по ходу речи
                    if not awake:
                        partial = json.loads(rec.PartialResult()).get("partial", "")
                        if any(self._is_wake(w) for w in partial.split()):
                            awake = True
                            self.on_wake()
                    continue

                text = json.loads(rec.Result()).get("text", "").strip()
                if not text:
                    if awake and not armed_until:
                        awake = False
                        self.on_idle()
                    continue

                cmd = self._extract_command(text)

                if cmd is None:
                    if armed_until and time.monotonic() < armed_until:
                        armed_until = 0.0
                        awake = False
                        self.on_command(text)
                    elif awake:                       # ложное срабатывание
                        awake = False
                        self.on_idle()
                elif cmd == "":
                    # сказали только "джарвис": ждём команду следующей фразой
                    armed_until = time.monotonic() + self.command_timeout
                    if not awake:
                        awake = True
                        self.on_wake()
                else:
                    armed_until = 0.0
                    awake = False
                    self.on_command(cmd)


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