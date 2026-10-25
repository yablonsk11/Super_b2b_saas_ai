import dotenv
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    RESOURCE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).parent
else:
    RESOURCE_DIR = Path(__file__).parent
    APP_DIR = Path(__file__).parent

dotenv.load_dotenv(APP_DIR / ".env")

# Prefer heavier Vosk models if they are present locally.
# Example names:
#   ru: vosk-model-ru-0.42
#   en: vosk-model-en-us-0.42-gigaspeech
_DEFAULT_RU_MODEL = RESOURCE_DIR / "vosk-model-small-ru-0.22"
_DEFAULT_EN_MODEL = RESOURCE_DIR / "models" / "vosk-model-small-en-us-0.15"

if (RESOURCE_DIR / "vosk-model-ru-0.42").exists():
    _DEFAULT_RU_MODEL = RESOURCE_DIR / "vosk-model-ru-0.42"
if (RESOURCE_DIR / "models" / "vosk-model-en-us-0.42-gigaspeech").exists():
    _DEFAULT_EN_MODEL = RESOURCE_DIR / "models" / "vosk-model-en-us-0.42-gigaspeech"

VOSK_MODEL_PATH = os.getenv("VOSK_MODEL_PATH", str(_DEFAULT_RU_MODEL))
EN_VOSK_MODEL_PATH = os.getenv("EN_VOSK_MODEL_PATH", str(_DEFAULT_EN_MODEL))

GIGACHAT_CREDITNAILS = os.getenv("GIGACHAT_CREDITNAILS")
MAX_RULE_WORDS = 3          # правила только для коротких фраз


DISCOVERY_PORT = 37020
DEFAULT_SERVER_PORT = 8000

DISCOVERY_TIMEOUT = 3

DEMO_MODE = False

# Сколько максимум слушать команду после «Джарвис»
COMMAND_LISTEN_TIMEOUT = float(os.getenv("COMMAND_LISTEN_TIMEOUT", "8"))
# Пауза тишины после речи, после которой фразу считаем законченной
COMMAND_SILENCE_FINALIZE = float(os.getenv("COMMAND_SILENCE_FINALIZE", "1.1"))

# Включаем стандартный набор wake-слов
WAKE_WORDS = (
    "джарвис",
    "жарвис",
    "джарвиз",
    "жарвиз",
    "jarvis",
    "jarviss",
    "jervis",
    "вась",
    "вася",
    "васян",
    "васянь",
    "васень",
    "васик",
    "васюк",
)

PIPER_MODEL_PATH = os.getenv(
    "PIPER_MODEL_PATH",
    str(RESOURCE_DIR / "models" / "ru_RU-irina-medium.onnx"),
)
PIPER_BIN = os.getenv("PIPER_BIN", "/usr/bin/piper-tts")
FFPLAY_BIN = os.getenv("FFPLAY_BIN", "/usr/bin/ffplay")

# Продолжить с прежним prompt, если его ожидали в более крупной версии
RULES = """
Правила для парсинга голосовых команд Spotify-ассистента:
- Никогда не включай в query слова, которые были сказаны ДО wake-word ("джарвис", "jarvis").
- Если в фразе есть wake-word — обрабатывай только текст ПОСЛЕ wake-word.
- Если пользователь просит включить музыку, трек, артистa, композицию, альбом, плейлист, радио или "play" — action = "play".
- Если он просит поставить на паузу, остановить, замолчать, выключить звук, "mute", "stop", "pause" — action = "pause".
- Если продолжить воспроизведение — action = "resume".
- Если следующий/предыдущий трек — action = "next" или "previous".
- Если нужна громкость — action = "volume" и value от 0 до 100.
- Если команда не распознана, слишком короткая, пустая, или это просто "джарвис" — action = "none".
- Для play-команд делай web_search: ищи самый вероятный трек/артиста/альбом и возвращай короткий query без лишних слов.
- Для play используйте query = только название трека/артиста, без "включи", "мне", "пожалуйста", "the", "me".
- Если user request похож на "музыку" без конкретного названия — action = "none".
- Возвращай только JSON в формате {"action":"...","query":"...","value":0,"language":"ru|en|mixed"}.
"""

PROMPT = """
Ты — парсер голосовых команд Spotify-ассистента.

Важные правила:
1. НЕ бери в обработку слова ДО wake-word. Если слышно "привет джарвис включи ..." — обрабатывай только текст после "джарвис".
2. Если в тексте сказано только "джарвис" или "jarvis" без команды — верни {"action":"none"}.
3. Сначала распознай тип команды: play / pause / resume / next / previous / volume / none.
4. Для play-команд обязательно используй web_search, чтобы выбрать самый вероятный трек или артиста, который соответствует spoken request.
5. Для play-команды итоговый query должен быть коротким и чистым: без "включи", "вруби", "мне", "пожалуйста", "the", "me", "play".
6. Если запрос про музыку вообще, но без конкретного названия — action = "none".
7. Если запрос про паузу/стоп/выключи/mute/заткнись — action = "pause".
8. Если следующий/предыдущий/громкость/продолжить — action = "next" / "previous" / "volume" / "resume".
9. Если непонятно — {"action":"none"}.

На вход приходят ДВА независимых распознавания одной и той же фразы:
- RU — русский Vosk (хорошо слышит русскую речь и русские названия)
- EN — английский Vosk (хорошо слышит английские названия, русский часто искажает)

Твоя задача — вернуть ОДИН JSON без markdown и без пояснений.

Формат:
{"action":"play|pause|resume|next|previous|volume|seek|none","query":"...","value":0,"language":"ru|en|mixed"}

Правила выбора языка для query:
1. Если пользователь хочет РУССКИЙ трек/артиста — бери русскую формулировку из RU.
2. Если хочет АНГЛИЙСКИЙ трек/артиста — бери латинское написание из EN.
3. Если это общий запрос на музкальный плейлист/текущее воспроизведение — action = "play" и query = самый вероятный трек/артист из web_search.
4. Убери паразиты: ка, мне, please, the, me, include.
5. Непонятно → {"action":"none"}.

Прочие action:
- пауза/pause/stop/стоп/выключи/выруби/отключи/mute → pause
- продолж/resume/continue → resume
- следующ/далее/next → next
- предыдущ/previous/назад → previous
- громкость/volume + число → volume + value 0..100

Верни только JSON.
"""