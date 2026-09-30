import json
import os
from pathlib import Path

import requests


API_URL = "https://api.weeek.net/public/v1"
TOKEN = os.environ.get("WEEEK_TOKEN")

if not TOKEN:
    raise RuntimeError("Не найден WEEEK_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
}

OUTPUT_FILE = Path("weeek_tasks.json")
PAGE_SIZE = 20


def get_tasks_page(offset: int, per_page: int = PAGE_SIZE) -> dict:
    response = requests.get(
        f"{API_URL}/tm/tasks",
        headers=HEADERS,
        params={
            "offset": offset,
            "per_page": per_page,
        },
        timeout=60,
    )

    response.raise_for_status()

    payload = response.json()

    if payload.get("success") is not True:
        raise RuntimeError(
            "WEEEK API вернул неуспешный ответ:\n"
            + json.dumps(payload, ensure_ascii=False, indent=2)
        )

    return payload


def get_all_tasks() -> list[dict]:
    all_tasks = []
    offset = 0

    while True:
        payload = get_tasks_page(
            offset=offset,
            per_page=PAGE_SIZE,
        )

        tasks = payload.get("tasks") or []
        has_more = bool(payload.get("hasMore", False))

        if not isinstance(tasks, list):
            raise RuntimeError(
                "Поле tasks имеет неожиданный формат:\n"
                + json.dumps(payload, ensure_ascii=False, indent=2)
            )

        all_tasks.extend(tasks)

        first_id = tasks[0].get("id") if tasks else None
        last_id = tasks[-1].get("id") if tasks else None

        print(
            f"offset={offset}; "
            f"получено={len(tasks)}; "
            f"всего={len(all_tasks)}; "
            f"первая задача={first_id}; "
            f"последняя задача={last_id}; "
            f"hasMore={has_more}"
        )

        if not has_more:
            break

        if not tasks:
            raise RuntimeError(
                "API сообщил hasMore=true, но вернул пустой список tasks. "
                "Остановка предотвращает бесконечный цикл."
            )

        offset += len(tasks)

    return all_tasks


def save_tasks(tasks: list[dict]) -> None:
    OUTPUT_FILE.write_text(
        json.dumps(
            {
                "success": True,
                "count": len(tasks),
                "tasks": tasks,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    tasks = get_all_tasks()
    save_tasks(tasks)

    projects = {}
    completed_count = 0
    active_count = 0

    for task in tasks:
        project_id = task.get("projectId")
        projects[project_id] = projects.get(project_id, 0) + 1

        if task.get("isCompleted"):
            completed_count += 1
        else:
            active_count += 1

    print()
    print(f"Всего задач: {len(tasks)}")
    print(f"Активных: {active_count}")
    print(f"Завершённых: {completed_count}")
    print(f"Проектов: {len(projects)}")
    print(f"Файл сохранён: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
