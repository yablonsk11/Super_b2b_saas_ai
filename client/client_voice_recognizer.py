import queue
import gigachat
from gigachat.models import ChatCompletionRequest, ChatMessage, ChatToolConfig
import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel
import threading
from array import array
import difflib
import time
import json
import re
import subprocess
import os
import tempfile
import random

from config import (
    VOSK_MODEL_PATH,
    EN_VOSK_MODEL_PATH,
    RULES,
    PROMPT,
    GIGACHAT_CREDITNAILS,
    WAKE_WORDS,
    PIPER_BIN,
    PIPER_MODEL_PATH,
    FFPLAY_BIN,
    COMMAND_LISTEN_TIMEOUT,
    COMMAND_SILENCE_FINALIZE,
)


# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------

class TTSPlayer:
    """Локальный TTS через Piper. Один голос в очереди, без обрезки фраз."""

    def __init__(
        self,
        piper_bin=PIPER_BIN,
        piper_model=PIPER_MODEL_PATH,
        ffplay_bin=FFPLAY_BIN,
        on_speaking=None,
    ):
        self.piper_bin = piper_bin
        self.piper_model = piper_model
        self.ffplay_bin = ffplay_bin
        self.on_speaking = on_speaking or (lambda active: None)
        self._queue = queue.Queue()
        self._speaking = threading.Event()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    @property
    def is_speaking(self) -> bool:
        return self._speaking.is_set() or not self._queue.empty()

    def _worker_loop(self):
        while True:
            text = self._queue.get()
            if text is None:
                break
            self._speaking.set()
            try:
                self.on_speaking(True)
                self._speak_sync(text)
            finally:
                self._speaking.clear()
                if self._queue.empty():
                    self.on_speaking(False)
                self._queue.task_done()

    def is_available(self) -> bool:
        if not self.piper_bin or not os.path.exists(self.piper_bin):
            return False
        if not self.piper_model or not os.path.exists(self.piper_model):
            return False
        return os.path.exists(f"{self.piper_model}.json")

    def _speak_sync(self, text: str):
        if not text or not text.strip() or not self.is_available():
            print(f"[TTS] skip: empty={not bool(text and text.strip())} available={self.is_available()}")
            return
        text = text.strip()
        print(f"[TTS] speak: {text[:120]}")
        try:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".txt", delete=False, encoding="utf-8"
            ) as src:
                src.write(text)
                src_path = src.name
            wav_path = src_path + ".wav"
            cmd = [
                self.piper_bin,
                "-m", self.piper_model,
                "-c", f"{self.piper_model}.json",
                "-f", wav_path,
                "-i", src_path,
            ]
            print(f"[TTS] piper cmd: {' '.join(cmd)}")
            piper_result = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
            print(f"[TTS] piper rc={piper_result.returncode} stderr={piper_result.stderr[:200]}")
            if os.path.exists(wav_path) and os.path.exists(self.ffplay_bin):
                ffplay_cmd = [
                    self.ffplay_bin,
                    "-autoexit",
                    "-nodisp",
                    "-hide_banner",
                    "-loglevel", "error",
                    "-volume", "100",
                    wav_path,
                ]
                print(f"[TTS] ffplay cmd: {' '.join(ffplay_cmd)}")
                ffplay_result = subprocess.run(
                    ffplay_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                )
                print(f"[TTS] ffplay rc={ffplay_result.returncode} stderr={ffplay_result.stderr[:200]}")
            for path in (src_path, wav_path):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except OSError:
                    pass
        except Exception as e:
            print(f"[TTS] exception: {e}")

    def speak(self, text: str):
        if not text or not text.strip():
            return
        print(f"[TTS] queued: {text.strip()[:120]}")
        self._queue.put(text.strip())

    def clear(self):
        """Сбрасывает очередь, чтобы не копить старые фразы."""
        try:
            while True:
                self._queue.get_nowait()
                self._queue.task_done()
        except queue.Empty:
            pass


# ---------------------------------------------------------------------------
# Bilingual helpers
# ---------------------------------------------------------------------------

_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
_LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)
_DROP_LEADING = frozenset({
    # wake
    "джарвис", "жарвис", "джарвиз", "жарвиз", "jarvis", "jarviss", "jervis",
    # play / mishears
    "включи", "вруби", "поставь", "запусти", "открой",
    "play", "start", "launch", "include", "inch", "which",
    # fillers
    "ка", "мне", "пожалуйста", "давай", "сейчас", "быстро",
    "track", "song", "the", "a", "an", "me", "please", "some", "on",
    "музыку", "песню", "трек", "композиции", "композиция",
    "turn",  # leftover from "turn on"
})
_FILLER_WORDS = _DROP_LEADING
_COMMAND_HINTS = (
    "включи", "вруби", "поставь", "запусти", "пауза", "стоп",
    "продолж", "следующ", "далее", "предыдущ", "громк", "тише",
    "play", "pause", "stop", "resume", "continue", "next", "previous",
    "volume", "seek", "include",
)


def _cyrillic_count(text: str) -> int:
    return len(_CYRILLIC_RE.findall(text or ""))


def _latin_count(text: str) -> int:
    return len(_LATIN_RE.findall(text or ""))


def _avg_confidence(payload: dict) -> float:
    words = payload.get("result") or []
    if not words:
        return 0.35 if payload.get("text") else 0.0
    confs = [float(w.get("conf", 0.0)) for w in words if "conf" in w]
    return sum(confs) / len(confs) if confs else 0.35


def _score_transcript(text: str, conf: float) -> float:
    if not text:
        return -1.0
    score = conf * 2.0 + len(text.split()) * 0.15
    lower = text.lower()
    if any(h in lower for h in _COMMAND_HINTS):
        score += 1.5
    # Slight preference for mixed (both scripts) — typical Jarvis play commands
    if _cyrillic_count(text) and _latin_count(text):
        score += 0.8
    return score


def _bare_word(word: str) -> str:
    return re.sub(r"[^\w'-]", "", word, flags=re.UNICODE).lower()


def _extract_music_query(text: str) -> str:
    """Срезает wake/команду/паразитов слева и возвращает поисковый query."""
    if not text:
        return ""
    words = text.strip().split()
    while words and _bare_word(words[0]) in _DROP_LEADING:
        words.pop(0)
    # "turn on X" уже частично разобран; добиваем "on"
    while words and _bare_word(words[0]) in _DROP_LEADING:
        words.pop(0)
    kept = []
    for w in words:
        if _bare_word(w) in _DROP_LEADING and not kept:
            continue
        kept.append(w)
    return " ".join(kept).strip(" ,.-")


def _clean_query(query: str) -> str:
    return _extract_music_query(query)


def _has_play_intent(text: str) -> bool:
    lower = (text or "").lower()
    return any(
        v in lower
        for v in (
            "включи", "вруби", "поставь", "запусти", "открой",
            "play", "turn on", "start", "launch", "include",
        )
    )


def format_dual_transcript(ru_text: str, en_text: str) -> str:
    """Единый payload для GigaChat: оба варианта STT без потери языка."""
    ru = (ru_text or "").strip()
    en = (en_text or "").strip()
    if ru and en:
        return f"RU: {ru}\nEN: {en}"
    return ru or en


def parse_dual_transcript(text: str) -> tuple[str, str]:
    """Достаёт RU/EN из dual-payload или возвращает (text, "")."""
    raw = (text or "").strip()
    if not raw:
        return "", ""
    if "RU:" in raw and "EN:" in raw:
        ru_m = re.search(r"RU:\s*(.*?)(?:\nEN:|$)", raw, re.IGNORECASE | re.DOTALL)
        en_m = re.search(r"EN:\s*(.*)$", raw, re.IGNORECASE | re.DOTALL)
        ru = (ru_m.group(1).strip() if ru_m else "")
        en = (en_m.group(1).strip() if en_m else "")
        return ru, en
    return raw, ""


def _looks_like_control(text: str) -> bool:
    lower = (text or "").lower()
    if not lower or _has_play_intent(lower):
        return False
    return any(
        k in lower
        for k in (
            "пауза", "pause", "stop", "стоп",
            "продолж", "resume", "continue",
            "следующ", "далее", "next", "скип",
            "предыдущ", "previous", "назад",
            "громк", "volume", "тише",
        )
    )


def merge_bilingual(ru_text: str, en_text: str, ru_conf: float = 0.0, en_conf: float = 0.0) -> str:
    """
    Для музыки — оба транскрипта (решает GigaChat + web_search).
    Для простых команд — один лучший транскрипт, без склейки.
    """
    ru = (ru_text or "").strip()
    en = (en_text or "").strip()
    if not ru and not en:
        return ""
    if not ru:
        return en
    if not en:
        return ru

    if _looks_like_control(ru) or _looks_like_control(en):
        if _score_transcript(ru, ru_conf) >= _score_transcript(en, en_conf):
            return ru
        return en

    if _has_play_intent(ru) or _has_play_intent(en):
        return format_dual_transcript(ru, en)

    # Разные гипотезы с кириллицей/латиницей — пусть GigaChat разберёт
    if _cyrillic_count(ru) >= 3 and _latin_count(en) >= 3 and ru.lower() != en.lower():
        return format_dual_transcript(ru, en)

    if _score_transcript(ru, ru_conf) >= _score_transcript(en, en_conf):
        return ru
    return en


def _strip_before_wake(text: str) -> str:
    """Отбрасывает всё, что было сказано до wake-word, и оставляет только команду после него."""
    raw = (text or "").strip()
    if not raw:
        return ""
    tokens = re.sub(r"\s+", " ", raw).split()
    wake_words = [w.lower() for w in WAKE_WORDS]
    for idx in range(len(tokens) - 1, -1, -1):
        token = re.sub(r"[^a-zа-яё]", "", tokens[idx].lower())
        if token in wake_words or any(
            difflib.SequenceMatcher(None, token, w).ratio() >= 0.7 for w in wake_words
        ):
            return " ".join(tokens[idx + 1:]).strip()
    return raw


# ---------------------------------------------------------------------------
# Voice listener
# ---------------------------------------------------------------------------

class VoiceListener:
    """Один поток аудио → два Vosk (RU+EN) → накопление фразы → команда."""

    def __init__(
        self,
        model_path=VOSK_MODEL_PATH,
        en_model_path=EN_VOSK_MODEL_PATH,
        wake_words=WAKE_WORDS,
        on_wake=None,
        on_idle=None,
        on_command=None,
        on_level=None,
        on_error=None,
        command_timeout=COMMAND_LISTEN_TIMEOUT,
        silence_finalize=COMMAND_SILENCE_FINALIZE,
        samplerate=16000,
        wake_threshold=0.73,
    ):
        SetLogLevel(-1)
        self.model = Model(model_path)
        self.en_model = Model(en_model_path) if os.path.exists(en_model_path) else None
        self.wake_words = [w.lower() for w in wake_words]
        self.on_wake = on_wake or (lambda: None)
        self.on_idle = on_idle or (lambda: None)
        self.on_command = on_command or (lambda text: None)
        self.on_level = on_level or (lambda x: None)
        self.on_error = on_error or (lambda msg: None)
        self.command_timeout = float(command_timeout)
        self.silence_finalize = float(silence_finalize)
        self.samplerate = samplerate
        self.wake_threshold = wake_threshold
        self._audio = queue.Queue()
        self._stop = threading.Event()
        self._muted = threading.Event()
        self._reset_recognizers = threading.Event()
        self._thread = None

    def set_muted(self, muted: bool):
        """Глушит микрофон на время TTS, чтобы не ловить эхо."""
        if muted:
            self._muted.set()
            self._drain_audio()
        else:
            self._drain_audio()
            self._reset_recognizers.set()
            self._muted.clear()

    def _drain_audio(self):
        try:
            while True:
                self._audio.get_nowait()
        except queue.Empty:
            pass

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = (text or "").lower().strip()
        text = text.replace("’", "'").replace("`", "'")
        text = re.sub(r"[\u2010-\u2015]", "-", text)
        return re.sub(r"\s+", " ", text)

    @staticmethod
    def find_input_device(prefer=("pipewire", "pulse", "default")):
        for name in prefer:
            for i in range(64):
                try:
                    d = sd.query_devices(i)
                except UnicodeDecodeError:
                    continue
                except sd.PortAudioError:
                    break
                if d["max_input_channels"] > 0 and d["name"].lower() == name:
                    return i
        return None

    def _is_wake(self, word: str) -> bool:
        cleaned = self._normalize_text(word)
        if not cleaned:
            return False
        thr = self.wake_threshold
        return any(
            cleaned == w
            or difflib.SequenceMatcher(None, cleaned, w).ratio() >= thr
            for w in self.wake_words
        )

    def _contains_wake_word(self, text: str) -> bool:
        if not text:
            return False
        return any(self._is_wake(w) for w in self._normalize_text(text).split())

    def _strip_all_wake_words(self, text: str) -> str:
        """Убирает ВСЕ вхождения wake-слова, не только ведущее."""
        if not text or not text.strip():
            return ""
        words = text.strip().split()
        norm = self._normalize_text(text).split()
        kept = []
        for i, w in enumerate(norm):
            if self._is_wake(w):
                continue
            kept.append(words[i])
        return " ".join(kept).strip(" ,.-")

    def _after_wake(self, text: str) -> str:
        """Убирает текст ДО wake и returns only the post-wake command."""
        if not text:
            return ""
        cleaned = self._normalize_text(text)
        words = cleaned.split()
        for idx, token in enumerate(words):
            if self._is_wake(token):
                return " ".join(words[idx + 1:]).strip()
        return cleaned

    def _append_unique(self, bucket: list[str], piece: str):
        piece = (piece or "").strip()
        if not piece:
            return
        if self._is_wake_only(piece):
            return
        if bucket and self._normalize_text(bucket[-1]) == self._normalize_text(piece):
            return
        joined = self._normalize_text(" ".join(bucket))
        if joined and self._normalize_text(piece) in joined:
            return
        bucket.append(piece)

    def _emit_accumulated(self, ru_parts: list[str], en_parts: list[str]) -> bool:
        ru = self._after_wake(self._strip_all_wake_words(" ".join(ru_parts).strip()))
        en = self._after_wake(self._strip_all_wake_words(" ".join(en_parts).strip()))
        print(f"[LISTEN] accumulation ru={ru!r} en={en!r}")
        if self._is_wake_only(ru, en):
            return False
        if not ru and not en:
            return False
        payload = merge_bilingual(ru, en)
        payload = (payload or "").strip()
        print(f"[LISTEN] merged payload={payload!r}")
        if not payload or self._is_wake_only(payload):
            return False
        ru_p, en_p = parse_dual_transcript(payload)
        if ru_p or en_p:
            if self._is_wake_only(ru_p, en_p):
                return False
        self.on_command(payload)
        return True

    def _callback(self, indata, frames, time_info, status):
        if self._muted.is_set():
            self.on_level(0.0)
            return
        data = bytes(indata)
        self._audio.put(data)
        samples = array("h", data)
        if samples:
            rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
            self.on_level(min(1.0, rms / 4000))

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _make_recognizer(self, model: Model) -> KaldiRecognizer:
        rec = KaldiRecognizer(model, self.samplerate)
        rec.SetWords(True)
        return rec

    def _read_result(self, rec: KaldiRecognizer, final: bool = False) -> tuple[str, float]:
        raw = rec.FinalResult() if final else rec.Result()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return "", 0.0
        return (payload.get("text") or "").strip(), _avg_confidence(payload)

    def _run(self):
        rec_ru = self._make_recognizer(self.model)
        rec_en = self._make_recognizer(self.en_model) if self.en_model else None
        armed_until = 0.0
        silence_until = 0.0
        awake = False
        ru_parts: list[str] = []
        en_parts: list[str] = []

        def _reset_listen():
            nonlocal awake, armed_until, silence_until, ru_parts, en_parts
            awake = False
            armed_until = 0.0
            silence_until = 0.0
            ru_parts = []
            en_parts = []

        def _arm():
            nonlocal awake, armed_until, silence_until, ru_parts, en_parts
            awake = True
            armed_until = time.monotonic() + self.command_timeout
            silence_until = 0.0
            ru_parts = []
            en_parts = []
            self.on_wake()

        def _try_finalize(force: bool = False) -> bool:
            nonlocal awake, armed_until, silence_until, ru_parts, en_parts
            now = time.monotonic()
            if not awake:
                return False
            ready = force or (silence_until and now >= silence_until)
            timed_out = armed_until and now >= armed_until
            if not ready and not timed_out:
                return False
            if ru_parts or en_parts:
                emitted = self._emit_accumulated(ru_parts, en_parts)
                _reset_listen()
                if not emitted:
                    self.on_idle()
                return emitted
            if timed_out:
                _reset_listen()
                self.on_idle()
            return False

        try:
            with sd.RawInputStream(
                samplerate=self.samplerate,
                blocksize=1600,
                dtype="int16",
                channels=1,
                device=self.find_input_device(),
                callback=self._callback,
            ):
                while not self._stop.is_set():
                    if self._reset_recognizers.is_set():
                        self._reset_recognizers.clear()
                        try:
                            rec_ru.Reset()
                            if rec_en:
                                rec_en.Reset()
                        except Exception:
                            pass
                        if awake:
                            _reset_listen()
                            self.on_idle()

                    try:
                        data = self._audio.get(timeout=0.15)
                    except queue.Empty:
                        _try_finalize()
                        continue

                    if self._muted.is_set():
                        continue

                    # Тишина после речи → пора собрать накопленное в команду
                    _try_finalize()

                    ru_done = rec_ru.AcceptWaveform(data)
                    en_done = rec_en.AcceptWaveform(data) if rec_en else False

                    if not ru_done and not en_done:
                        partial = ""
                        try:
                            partial = json.loads(rec_ru.PartialResult()).get("partial", "") or ""
                        except json.JSONDecodeError:
                            pass
                        if rec_en and not partial.strip():
                            try:
                                partial = json.loads(rec_en.PartialResult()).get("partial", "") or ""
                            except json.JSONDecodeError:
                                pass
                        cleaned = self._normalize_text(partial)
                        if cleaned:
                            if not awake and self._contains_wake_word(cleaned):
                                _arm()
                            elif awake:
                                # речь идёт — сдвигаем дедлайн тишины
                                silence_until = time.monotonic() + self.silence_finalize
                                armed_until = max(
                                    armed_until,
                                    time.monotonic() + max(3.0, self.silence_finalize + 1.0),
                                )
                        else:
                            _try_finalize()
                        continue

                    # Один из моделей закончил фразу — добираем вторую через FinalResult
                    if ru_done:
                        ru_text, _ru_conf = self._read_result(rec_ru, final=False)
                    else:
                        ru_text, _ru_conf = self._read_result(rec_ru, final=True)

                    if rec_en:
                        if en_done:
                            en_text, _en_conf = self._read_result(rec_en, final=False)
                        else:
                            en_text, _en_conf = self._read_result(rec_en, final=True)
                    else:
                        en_text, _en_conf = "", 0.0

                    combined_for_wake = self._normalize_text(
                        f"{ru_text} {en_text}".strip()
                    )
                    has_wake = self._contains_wake_word(combined_for_wake)
                    wake_only = self._is_wake_only(ru_text, en_text)

                    if not awake:
                        if not has_wake:
                            continue
                        _arm()
                        if wake_only:
                            # Только «Джарвис» — ждём саму команду
                            continue
                        # «Джарвис включи …» в одной фразе — копим, не шлём сразу
                        self._append_unique(ru_parts, self._strip_all_wake_words(ru_text))
                        self._append_unique(en_parts, self._strip_all_wake_words(en_text))
                        silence_until = time.monotonic() + self.silence_finalize
                        continue

                    # Уже слушаем команду
                    if wake_only:
                        # Повторный wake / эхо имени — не команда
                        armed_until = time.monotonic() + self.command_timeout
                        silence_until = 0.0
                        self.on_wake()
                        continue

                    self._append_unique(ru_parts, self._strip_all_wake_words(ru_text))
                    self._append_unique(en_parts, self._strip_all_wake_words(en_text))
                    silence_until = time.monotonic() + self.silence_finalize
                    armed_until = max(
                        armed_until,
                        time.monotonic() + max(3.0, self.silence_finalize + 1.0),
                    )
        except Exception as e:
            self.on_error(f"Ошибка распознавания: {e}")

    def _is_wake_only(self, *texts: str) -> bool:
        """True, если после удаления wake-слов в тексте ничего ценного не осталось."""
        for text in texts:
            rest = self._strip_all_wake_words(text or "")
            rest = self._normalize_text(rest)
            rest = re.sub(r"\b(ru|en):\s*", "", rest).strip()
            if not rest:
                continue
            tokens = [t for t in rest.split() if t not in ("ru", "en")]
            if not tokens:
                continue
            if len("".join(tokens)) >= 2 and not all(self._is_wake(t) for t in tokens):
                return False
        return True


# ---------------------------------------------------------------------------
# Command processor
# ---------------------------------------------------------------------------

_PLAY_PREFIXES = (
    "включи ка мне",
    "включи мне",
    "включи-ка",
    "включи ка",
    "включи",
    "вруби мне",
    "вруби",
    "поставь мне",
    "поставь",
    "запусти",
    "открой",
    "play me",
    "play",
    "turn on",
    "start",
    "launch",
)

_SPEECH_PLAY = (
    "Хорошо, босс, включаю {query}.",
    "Есть, босс, ставлю {query}.",
    "Сейчас, босс — {query}.",
    "Понял, босс, включаю {query}.",
)


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

    def generate_response_text(self, command: dict, original_text: str = "") -> str:
        if not isinstance(command, dict):
            return "Не расслышал, босс, повторите."

        action = command.get("action")
        query = str(command.get("query") or "").strip()
        value = command.get("value")

        if action == "play":
            label = query or "музыку"
            return random.choice(_SPEECH_PLAY).format(query=label)
        if action == "pause":
            return random.choice(("Пауза, босс.", "Ставлю на паузу, босс."))
        if action == "resume":
            return random.choice(("Продолжаем, босс.", "Снимаю с паузы, босс."))
        if action == "next":
            return random.choice(("Следующий трек, босс.", "Переключаю дальше."))
        if action == "previous":
            return random.choice(("Предыдущий трек, босс.", "Листаю назад."))
        if action == "volume":
            return f"Громкость {value if value is not None else 50}, босс."
        if action == "seek":
            return f"Перематываю на {value if value is not None else 0} секунд."
        return "Не расслышал, босс, повторите."

    @staticmethod
    def _normalize_command_text(text: str) -> str:
        text = (text or "").lower().strip()
        text = text.replace("’", "'").replace("`", "'")
        text = re.sub(r"\s+", " ", text)
        return text

    @staticmethod
    def _safe_json(data):
        if isinstance(data, dict):
            return data
        if isinstance(data, str):
            raw = data.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                match = re.search(r"\{.*\}", raw, re.DOTALL)
                if match:
                    try:
                        obj = json.loads(match.group(0))
                        if isinstance(obj, dict):
                            return obj
                    except json.JSONDecodeError:
                        pass
        return {"action": "none"}

    @staticmethod
    def _response_text(response) -> str:
        """Собирает текст из ответа primary chat API."""
        try:
            messages = getattr(response, "messages", None) or []
            parts = []
            for msg in messages:
                role = getattr(msg, "role", None)
                if role and role not in ("assistant", "model"):
                    continue
                for part in getattr(msg, "content", None) or []:
                    t = getattr(part, "text", None)
                    if t:
                        parts.append(t)
            if parts:
                return "\n".join(parts).strip()
        except Exception:
            pass
        return ""

    @staticmethod
    def _fallback_control(text: str) -> dict:
        """Только pause/next/resume/volume — play сюда НЕ входит."""
        normalized = CommandProcessor._normalize_command_text(text)
        normalized = re.sub(r"\b(ru|en):\s*", "", normalized)
        normalized = _strip_before_wake(normalized) if normalized else ""
        if not normalized:
            return {"action": "none"}

        if _has_play_intent(normalized):
            return {"action": "none"}

        if any(k in normalized for k in ("выключи", "выруби", "mute", "заглуш", "заткни", "стоп", "stop", "пауза")):
            return {"action": "pause"}
        if any(k in normalized for k in ("следующ", "далее", "next", "скип")):
            return {"action": "next"}
        if any(k in normalized for k in ("предыдущ", "previous", "назад")):
            return {"action": "previous"}
        if any(k in normalized for k in ("продолж", "resume", "continue")):
            return {"action": "resume"}
        if any(k in normalized for k in ("громч", "volume", "тише", "громкость")):
            nums = re.findall(r"\b(\d{1,3})\b", normalized)
            value = int(nums[0]) if nums else 80
            return {"action": "volume", "value": max(0, min(100, value))}
        return {"action": "none"}

    @staticmethod
    def _fallback_play(ru: str, en: str) -> dict:
        if not (_has_play_intent(ru) or _has_play_intent(en)):
            return {"action": "none"}
        ru_q = _extract_music_query(ru)
        en_q = _extract_music_query(en)
        play_ru = _has_play_intent(ru)
        play_en = _has_play_intent(en)

        if not (play_ru or play_en or ru_q or en_q):
            return {"action": "none"}

        ru_cyr = _cyrillic_count(ru_q)
        ru_lat = _latin_count(ru_q)
        en_lat = _latin_count(en_q)

        if ru_q and ru_cyr >= 3 and ru_cyr >= ru_lat:
            return {"action": "play", "query": ru_q, "language": "ru"}
        if en_q and en_lat >= 3:
            return {"action": "play", "query": en_q, "language": "en"}
        if ru_q and ru_lat >= 3:
            return {"action": "play", "query": ru_q, "language": "en"}
        if ru_q:
            return {"action": "play", "query": ru_q, "language": "ru"}
        if en_q:
            return {"action": "play", "query": en_q, "language": "en"}
        return {"action": "none"}

    def _ask_gigachat(self, ru: str, en: str, raw: str) -> dict:
        cleaned_raw = _strip_before_wake(raw)
        cleaned_ru = _strip_before_wake(ru)
        cleaned_en = _strip_before_wake(en)
        user_payload = (
            "Распознавание одной фразы двумя движками STT.\n"
            f"RU: {cleaned_ru or '—'}\n"
            f"EN: {cleaned_en or '—'}\n"
            f"RAW: {cleaned_raw or '—'}\n\n"
            "Через web_search определи, какой это трек/артист и на каком языке "
            "должен быть query для Spotify. Если это не play-фраза, а команда "
            "pause/resume/next/previous/volume, верни соответствующий action. "
            "Верни только JSON."
        )
        request = ChatCompletionRequest(
            model="GigaChat-2",
            messages=[
                ChatMessage(role="system", content=self.prompt),
                ChatMessage(role="user", content=user_payload),
            ],
            tools=["web_search"],
            tool_config=ChatToolConfig(mode="auto"),
            profanity_check=False,
        )
        response = self.client.chat.create(request)
        answer = self._response_text(response)
        obj = self._safe_json(answer)
        if obj.get("action") == "play" and obj.get("query"):
            q = str(obj["query"]).strip()
            obj["query"] = _extract_music_query(q) or q
        return obj

    def process(self, text: str) -> dict:
        raw = (text or "").strip()
        if not raw:
            return {"action": "none"}

        raw = _strip_before_wake(raw)
        if not raw:
            return {"action": "none"}

        ru, en = parse_dual_transcript(raw)
        ru = _strip_before_wake(ru)
        en = _strip_before_wake(en)
        if not ru and not en:
            return {"action": "none"}

        for candidate in (ru, en, raw):
            control = self._fallback_control(candidate)
            if control.get("action") != "none":
                return control

        try:
            obj = self._ask_gigachat(ru, en, raw)
            if obj.get("action") == "play" and not (_has_play_intent(ru) or _has_play_intent(en) or _has_play_intent(raw)):
                obj = {"action": "none"}
            if obj.get("action") != "none":
                return obj
        except Exception as e:
            print("Ошибка GigaChat:", e)

        play = self._fallback_play(ru, en)
        if play.get("action") != "none":
            return play
        return self._fallback_control(ru or en or raw)
