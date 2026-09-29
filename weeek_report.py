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
            text = response.read().decode("utf-8")
            return response.status, json.loads(text)

    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"HTTP {error.code}: {path}")
        print(body)
        return error.code, None

    except URLError as error:
        print(f"Ошибка соединения: {error.reason}")
        sys.exit(1)


paths = [
    "/tm/workspaces",
    "/tm/projects",
    "/tm/boards",
    "/tm/board-columns",
    "/tm/tasks",
]

result = {}

for path in paths:
    print(f"Запрос: {path}")
    status, data = get_json(path)

    result[path] = {
        "status": status,
        "data": data,
    }

with open("weeek_api_data.json", "w", encoding="utf-8") as file:
    json.dump(result, file, ensure_ascii=False, indent=2)

print("Результат сохранен в weeek_api_data.json")
