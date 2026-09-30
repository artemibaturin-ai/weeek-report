import csv
import html
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

API_URL = "https://api.weeek.net/public/v1"
TOKEN = os.environ.get("WEEEK_TOKEN")

if not TOKEN:
    raise RuntimeError("Не найден секрет WEEEK_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
}

PAGE_SIZE = 100
MAX_PAGES = 100


def request_json(path, params=None):
    response = requests.get(
        f"{API_URL}{path}",
        headers=HEADERS,
        params=params or {},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def find_records(payload, names):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for name in names:
        value = payload.get(name)

        if isinstance(value, list):
            return value

    for name in names:
        value = payload.get(name)

        if isinstance(value, dict):
            nested = find_records(value, names)

            if nested:
                return nested

    return []


def load_collection(path, names):
    records = []
    seen_ids = set()

    for page_number in range(1, MAX_PAGES + 1):
        payload = request_json(
            path,
            {
                "page": page_number,
                "limit": PAGE_SIZE,
            },
        )

        page_records = find_records(payload, names)

        if not page_records:
            break

        added = 0

        for record in page_records:
            if not isinstance(record, dict):
                continue

            record_id = record.get("id")

            if record_id is not None:
                record_key = str(record_id)

                if record_key in seen_ids:
                    continue

                seen_ids.add(record_key)

            records.append(record)
            added += 1

        if added == 0:
            break

        if len(page_records) < PAGE_SIZE:
            break

    return records


def load_tasks():
    errors = []

    for path in ("/tm/tasks", "/tasks"):
        try:
            return load_collection(
                path,
                (
                    "tasks",
                    "items",
                    "results",
                    "data",
                ),
            )
        except requests.HTTPError as error:
            errors.append(f"{path}: {error}")

    raise RuntimeError(
        "Не удалось получить задачи Weeek: "
        + " | ".join(errors)
    )


def load_projects():
    errors = []

    for path in ("/tm/projects", "/projects"):
        try:
            return load_collection(
                path,
                (
                    "projects",
                    "items",
                    "results",
                    "data",
                ),
            )
        except requests.HTTPError as error:
            errors.append(f"{path}: {error}")

    raise RuntimeError(
        "Не удалось получить проекты Weeek: "
        + " | ".join(errors)
    )


def first(record, keys, default=""):
    if not isinstance(record, dict):
        return default

    for key in keys:
        value = record.get(key)

        if value is not None and value != "":
            return value

    return default


def text(value, default=""):
    if isinstance(value, dict):
        return str(
            first(
                value,
                (
                    "name",
                    "title",
                    "label",
                    "text",
                    "id",
                ),
                default,
            )
        )

    if value is None or value == "":
        return default

    return str(value)


def task_id(task):
    return first(
        task,
        (
            "id",
            "taskId",
            "task_id",
        ),
        "",
    )


def task_title(task):
    return text(
        first(
            task,
            (
                "title",
                "name",
                "text",
            ),
            "Без названия",
        ),
        "Без названия",
    )


def task_project_id(task):
    project = task.get("project")

    if isinstance(project, dict):
        return first(
            project,
            (
                "id",
                "projectId",
            ),
            "",
        )

    return first(
        task,
        (
            "projectId",
            "project_id",
        ),
        "",
    )


def task_project_name(task, projects_by_id):
    project = task.get("project")

    if isinstance(project, str) and project:
        return project

    if isinstance(project, dict):
        return text(project, "Без проекта")

    project_id = task_project_id(task)

    if project_id != "":
        project_record = projects_by_id.get(str(project_id))

        if project_record:
            return text(project_record, "Без проекта")

    return "Без проекта"


def task_status(task):
    status = task.get("status")

    if isinstance(status, str) and status:
        return status

    if isinstance(status, dict):
        return text(status, "Не указан")

    fallback = first(
        task,
        (
            "statusName",
            "status_name",
            "state",
            "column",
        ),
        "",
    )

    return text(fallback, "Не указан")


def task_status_id(task):
    status = task.get("status")

    if isinstance(status, dict):
        return first(
            status,
            (
                "id",
                "statusId",
            ),
            "",
        )

    return first(
        task,
        (
            "statusId",
            "status_id",
            "stateId",
            "columnId",
        ),
        "",
    )


def task_is_completed(task):
    value = first(
        task,
        (
            "isCompleted",
            "is_completed",
            "completed",
        ),
        False,
    )

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value == 1

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "да",
        }

    return task_status(task).strip().lower() in {
        "выполнено",
        "завершено",
        "готово",
        "done",
        "completed",
        "complete",
    }


def task_overdue(task):
    value = first(
        task,
        (
            "overdue",
            "overdueDays",
            "overdue_days",
        ),
        0,
    )

    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def task_due_date(task):
    return first(
        task,
        (
            "dueDate",
            "due_date",
            "deadline",
            "date",
        ),
        "",
    )


def task_parent_id(task):
    value = first(
        task,
        (
            "parentId",
            "parent_id",
            "parentTaskId",
            "parent_task_id",
        ),
        "",
    )

    if isinstance(value, dict):
        return first(
            value,
            (
                "id",
                "taskId",
            ),
            "",
        )

    return value


def nested_tasks(task):
    result = []

    for key in (
        "subtasks",
        "subTasks",
        "children",
        "childTasks",
        "child_tasks",
    ):
        value = task.get(key)

        if isinstance(value, list):
            result.extend(
                item
                for item in value
                if isinstance(item, dict)
            )

        elif isinstance(value, dict):
