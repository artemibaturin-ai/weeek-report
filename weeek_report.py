import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TOKEN = os.environ.get("WEEEK_TOKEN")
BASE_URL = "https://api.weeek.net/public/v1"

if not TOKEN:
    print("Ошибка: секрет WEEEK_TOKEN не передан")
    sys.exit(1)


def api_get(path, params):
    url = BASE_URL + path + "?" + urlencode(params)

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=60) as response:
            body = response.read().decode("utf-8")
            return {
                "url": url,
                "status": response.status,
                "body": json.loads(body),
            }

    except HTTPError as error:
        return {
            "url": url,
            "status": error.code,
            "body": error.read().decode("utf-8", errors="replace"),
        }

    except URLError as error:
        return {
            "url": url,
            "status": "connection_error",
            "body": str(error.reason),
        }


def summarize(result):
    body = result.get("body")

    if not isinstance(body, dict):
        return {
            "status": result.get("status"),
            "type": type(body).__name__,
        }

    tasks = body.get("tasks", [])

    return {
        "status": result.get("status"),
        "task_count": len(tasks),
        "first_ids": [task.get("id") for task in tasks[:10]],
        "last_ids": [task.get("id") for task in tasks[-10:]],
        "hasMore": body.get("hasMore"),
        "keys": list(body.keys()),
    }


def main():
    tests = [
        {"projectId": 2},
        {"projectId": 2, "page": 1},
        {"projectId": 2, "page": 2},
        {"projectId": 2, "page": 3},
        {"projectId": 2, "limit": 100},
        {"projectId": 2, "limit": 100, "offset": 0},
        {"projectId": 2, "limit": 100, "offset": 100},
        {"projectId": 2, "limit": 100, "offset": 200},
        {"projectId": 2, "perPage": 100, "page": 1},
        {"projectId": 2, "perPage": 100, "page": 2},
        {"projectId": 2, "skip": 0},
        {"projectId": 2, "skip": 100},
        {"projectId": 2, "cursor": 0},
        {"projectId": 2, "completed": False},
        {"projectId": 2, "isCompleted": False},
    ]

    results = []

    for params in tests:
        result = api_get("/tm/tasks", params)

        item = {
            "params": params,
            "summary": summarize(result),
            "response": result,
        }

        results.append(item)

        print(params)
        print(item["summary"])

    with open("weeek_pagination_tests.json", "w", encoding="utf-8") as file:
        json.dump(results, file, ensure_ascii=False, indent=2)

    print("Создан файл weeek_pagination_tests.json")


if __name__ == "__main__":
    main()
