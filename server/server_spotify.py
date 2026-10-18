import time
import requests
from requests.auth import HTTPBasicAuth

from server_config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REFRESH_TOKEN,
)

SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"


class SpotifyError(Exception):
    """Ошибка при взаимодействии со Spotify API."""
    pass


class SpotifyController:
    def __init__(self):
        if not all([SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REFRESH_TOKEN]):
            raise SpotifyError(
                "Не заданы SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET "
                "или SPOTIFY_REFRESH_TOKEN в .env"
            )
        self._session = requests.Session()
        self._access_token = None
        self._expires_at = 0.0

    # ---------- авторизация ----------

    def _refresh_access_token(self):
        auth = HTTPBasicAuth(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
        data = {
            "grant_type": "refresh_token",
            "refresh_token": SPOTIFY_REFRESH_TOKEN,
        }
        r = self._session.post(SPOTIFY_TOKEN_URL, auth=auth, data=data, timeout=10)
        if r.status_code != 200:
            raise SpotifyError(f"Не удалось обновить токен Spotify: {r.text}")
        payload = r.json()
        self._access_token = payload["access_token"]
        self._expires_at = time.time() + payload.get("expires_in", 3600) - 60

    def _ensure_token(self):
        if not self._access_token or time.time() >= self._expires_at:
            self._refresh_access_token()

    def check(self):
        """Проверка авторизации при старте сервера. Бросает SpotifyError."""
        self._refresh_access_token()

    # ---------- низкоуровневый запрос ----------

    def _api(self, method, endpoint, **kwargs):
        self._ensure_token()
        url = f"{SPOTIFY_API_BASE}{endpoint}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self._access_token}"
        r = self._session.request(method, url, headers=headers, timeout=10, **kwargs)

        if r.status_code == 401:
            self._refresh_access_token()
            headers["Authorization"] = f"Bearer {self._access_token}"
            r = self._session.request(method, url, headers=headers, timeout=10, **kwargs)

        if r.status_code == 204:
            return None
        if r.status_code >= 400:
            raise SpotifyError(f"Spotify API {r.status_code}: {r.text}")
        if r.text:
            return r.json()
        return None

    # ---------- выполнение команд ----------

    def execute(self, command: dict):
        action = command.get("action")
        if action == "play":
            return self._play(query=command.get("query"))
        if action == "pause":
            return self._api("PUT", "/me/player/pause")
        if action == "resume":
            return self._api("PUT", "/me/player/play")
        if action == "next":
            return self._api("POST", "/me/player/next")
        if action == "previous":
            return self._api("POST", "/me/player/previous")
        if action == "volume":
            value = int(command.get("value", 50))
            value = max(0, min(100, value))
            return self._api("PUT", "/me/player/volume", params={"volume_percent": value})
        if action == "seek":
            seconds = float(command.get("value", 0))
            return self._seek_relative(seconds)
        raise SpotifyError(f"Неизвестное действие: {action}")

    def _seek_relative(self, seconds: float):
        playback = self._api("GET", "/me/player")
        if not playback or playback.get("is_playing") is None:
            raise SpotifyError("Нет активного воспроизведения для перемотки")
        current_ms = playback.get("progress_ms", 0)
        target_ms = max(0, current_ms + int(seconds * 1000))
        return self._api("PUT", "/me/player/seek", params={"position_ms": target_ms})

    def _play(self, query: str | None = None):
        if not query:
            return self._api("PUT", "/me/player/play")

        search = self._api(
            "GET",
            "/search",
            params={"q": query, "type": "track", "limit": 1},
        )
        tracks = search.get("tracks", {}).get("items", []) if search else []
        if tracks:
            uri = tracks[0]["uri"]
            return self._api("PUT", "/me/player/play", json={"uris": [uri]})

        search = self._api(
            "GET",
            "/search",
            params={"q": query, "type": "artist", "limit": 1},
        )
        artists = search.get("artists", {}).get("items", []) if search else []
        if artists:
            context_uri = artists[0]["uri"]
            return self._api("PUT", "/me/player/play", json={"context_uri": context_uri})

        raise SpotifyError(f"По запросу «{query}» ничего не найдено")
