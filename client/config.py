import dotenv
import os

dotenv.load_dotenv()
GIGACHAT_CREDITNAILS = os.getenv("GIGACHAT_CREDITNAILS")
MAX_RULE_WORDS = 3          # правила только для коротких фраз

VOSK_MODEL_PATH = "vosk-model-small-ru-0.22"

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