import json
import os
from pathlib import Path

import requests


API_URL = "https://api.weeek.net/public/v1"
TOKEN = os.environ.get("WEEEK_TOKEN")

if not TOKEN:
    raise RuntimeError("Не найден WEEEK_TOKEN")

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
}

attempts = [
    (
        "offset_limit",
        "/tm/tasks",
        {"offset": 0, "limit": 20},
    ),
    (
        "offset_per_page",
        "/tm/tasks",
        {"offset": 0, "per_page": 20},
    ),
    (
        "page_limit",
        "/tm/tasks",
        {"page": 1, "limit": 20},
    ),
    (
        "page_per_page",
        "/tm/tasks",
        {"page": 1, "per_page": 20},
    ),
]

results = []

for name, path, params in attempts:
    response = requests.get(
        f"{API_URL}{path}",
        headers=headers,
        params=params,
        timeout=60,
    )

    print(f"\n{name}")
    print(f"URL: {response.url}")
    print(f"HTTP: {response.status_code}")
    print(f"Body: {response.text[:1000]}")

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw": response.text}

    results.append(
        {
            "name": name,
            "url": response.url,
            "status": response.status_code,
            "payload": payload,
        }
    )

Path("weeek_api_probe.json").write_text(
    json.dumps(
        results,
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)
