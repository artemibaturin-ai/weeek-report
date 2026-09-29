import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

token = os.environ.get("WEEEK_TOKEN")

if not token:
    print("Ошибка: секрет WEEEK_TOKEN не передан")
    sys.exit(1)

base_url = "https://api.weeek.net/public/v1"

def get_json(path):
    request = Request(
        base_url + path,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))

    except HTTPError as error:
        print(f"Ошибка API: HTTP {error.code} при запросе {path}")
        print(error.read().decode("utf-8", errors="replace"))
        sys.exit(1)

    except URLError as error:
        print(f"Ошибка соединения: {error.reason}")
        sys.exit(1)

profile = get_json("/user/me")

with open("weeek_profile.json", "w", encoding="utf-8") as file:
    json.dump(profile, file, ensure_ascii=False, indent=2)

print("Авторизация Weeek работает.")
print("Профиль сохранен в weeek_profile.json")
