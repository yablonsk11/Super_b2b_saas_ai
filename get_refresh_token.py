# get_refresh_token.py — запустить один раз, скопировать refresh_token в .env
import urllib.parse
import requests
from requests.auth import HTTPBasicAuth

CLIENT_ID = "..."       # из Spotify Dashboard
CLIENT_SECRET = "..."
REDIRECT_URI = "http://localhost:8888/callback"
SCOPES = "user-modify-playback-state user-read-playback-state user-read-currently-playing"

auth_url = (
    "https://accounts.spotify.com/authorize?"
    + urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
    })
)
print("Откройте URL и разрешите доступ:\n", auth_url)

redirected = input("Вставьте полный URL, на который вас перенаправило: ").strip()
code = urllib.parse.parse_qs(urllib.parse.urlparse(redirected).query)["code"][0]

r = requests.post(
    "https://accounts.spotify.com/api/token",
    auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
    data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    },
)
print("refresh_token:", r.json()["refresh_token"])
