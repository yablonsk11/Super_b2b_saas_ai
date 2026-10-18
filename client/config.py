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
VOSK_MODEL_PATH = str(RESOURCE_DIR / "vosk-model-small-ru-0.22")

GIGACHAT_CREDITNAILS = os.getenv("GIGACHAT_CREDITNAILS")
MAX_RULE_WORDS = 3          # правила только для коротких фраз


DISCOVERY_PORT = 37020
DEFAULT_SERVER_PORT = 8000

DISCOVERY_TIMEOUT = 3

DEMO_MODE = False

RULES = {
    "следующ": {"action": "next"},
    "дальше": {"action": "next"},
    "предыдущ": {"action": "previous"},
    "назад": {"action": "previous"},
    "пауза": {"action": "pause"},
    "стоп": {"action": "pause"},
    "продолжить": {"action": "resume"},
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