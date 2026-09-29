import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

token = os.environ.get("WEEEK_TOKEN")

if not token:
    print("Ошибка: секрет WEEEK_TOKEN не передан")
    sys.exit(1)

url = "https://api.weeek.net/public/v1/user/me"

request = Request(
    url,
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    },
    method="GET",
)

try:
    with urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))

    print("Авторизация Weeek работает.")
    print("Получен ответ API без вывода токена.")
    print(json.dumps(data, ensure_ascii=False, indent=2))

except HTTPError as error:
    print(f"Ошибка Weeek API: HTTP {error.code}")
    print(error.read().decode("utf-8", errors="replace"))
    sys.exit(1)

except URLError as error:
    print(f"Ошибка соединения: {error.reason}")
    sys.exit(1)
