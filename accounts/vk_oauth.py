import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from django.conf import settings


AUTHORIZE_URL = "https://oauth.vk.com/authorize"
TOKEN_URL = "https://oauth.vk.com/access_token"
API_URL = "https://api.vk.com/method/users.get"


class VKOAuthError(Exception):
    pass


def build_authorize_url(redirect_uri, state):
    query = urlencode({
        "client_id": settings.VK_CLIENT_ID,
        "display": "page",
        "redirect_uri": redirect_uri,
        "scope": "email",
        "response_type": "code",
        "v": settings.VK_API_VERSION,
        "state": state,
    })
    return f"{AUTHORIZE_URL}?{query}"


def fetch_json(url, params):
    query = urlencode(params)
    try:
        with urlopen(f"{url}?{query}", timeout=10) as response:
            payload = response.read().decode("utf-8")
    except URLError as exc:
        raise VKOAuthError("VK не ответил. Попробуйте позже.") from exc

    data = json.loads(payload)
    if "error" in data:
        error = data["error"]
        if isinstance(error, dict):
            message = error.get("error_msg") or error.get("error") or "Ошибка VK."
        else:
            message = str(error)
        raise VKOAuthError(message)
    return data


def exchange_code(code, redirect_uri):
    return fetch_json(TOKEN_URL, {
        "client_id": settings.VK_CLIENT_ID,
        "client_secret": settings.VK_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "code": code,
    })


def get_user_profile(access_token, user_id):
    data = fetch_json(API_URL, {
        "user_ids": user_id,
        "fields": "screen_name,photo_100",
        "access_token": access_token,
        "v": settings.VK_API_VERSION,
    })
    response = data.get("response") or []
    if not response:
        raise VKOAuthError("VK не вернул данные пользователя.")
    return response[0]
