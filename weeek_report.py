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


def find_list(value, keys):
    if isinstance(value, list):
        return value

    if not isinstance(value, dict):
        return []

    for key in keys:
        candidate = value.get(key)

        if isinstance(candidate, list):
            return candidate

    for key in keys:
        candidate = value.get(key)

        if isinstance(candidate, dict):
            result = find_list(candidate, keys)

            if result:
                return result

    return []


def load_collection(path):
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

        page_records = find_list(
            payload,
            (
                "tasks",
                "projects",
                "items",
                "results",
                "data",
            ),
        )

        if not page_records:
            break

        added = 0

        for record in page_records:
            if not isinstance(record, dict):
                continue

            record_id = record.get("id")

            if record_id is not None:
                key = str(record_id)

                if key in seen_ids:
                    continue

                seen_ids.add(key)

            records.append(record)
            added += 1

        if added == 0 or len(page_records) < PAGE_SIZE:
            break

    return records


def load_first_available(paths):
    errors = []

    for path in paths:
        try:
            return load_collection(path)
        except requests.HTTPError as error:
            errors.append(f"{path}: {error}")

    raise RuntimeError(
        "Не удалось получить данные Weeek: "
        + " | ".join(errors)
    )


def load_tasks():
    return load_first_available(
        (
            "/tm/tasks",
            "/tasks",
        )
    )


def load_projects():
    return load_first_available(
        (
            "/tm/projects",
            "/projects",
        )
    )


def first(record, keys, default=""):
    if not isinstance(record, dict):
        return default

    for key in keys:
        value = record.get(key)

        if value is not None and value != "":
            return value

    return default


def as_text(value, default=""):
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
    return as_text(
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
    project_value = task.get("project")

    if isinstance(project_value, dict):
        return first(
            project_value,
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
    project_value = task.get("project")

    if isinstance(project_value, str) and project_value:
        return project_value

    if isinstance(project_value, dict):
        return as_text(project_value, "Без проекта")

    current_project_id = task_project_id(task)

    if current_project_id != "":
        project = projects_by_id.get(str(current_project_id))

        if project:
            return as_text(project, "Без проекта")

    return "Без проекта"


def task_status(task):
    status_value = task.get("status")

    if isinstance(status_value, str) and status_value:
        return status_value

    if isinstance(status_value, dict):
        return as_text(status_value, "Не указан")

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

    return as_text(fallback, "Не указан")


def task_status_id(task):
    status_value = task.get("status")

    if isinstance(status_value, dict):
        return first(
            status_value,
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
    completed_value = first(
        task,
        (
            "isCompleted",
            "is_completed",
            "completed",
        ),
        False,
    )

    if isinstance(completed_value, bool):
        return completed_value

    if isinstance(completed_value, int):
        return completed_value == 1

    if isinstance(completed_value, str):
        return completed_value.strip().lower() in {
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
    overdue_value = first(
        task,
        (
            "overdue",
            "overdueDays",
            "overdue_days",
        ),
        0,
    )

    try:
        return int(overdue_value) > 0
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
    parent_value = first(
        task,
        (
            "parentId",
            "parent_id",
            "parentTaskId",
            "parent_task_id",
        ),
        "",
    )

    if isinstance(parent_value, dict):
        return first(
            parent_value,
            (
                "id",
                "taskId",
            ),
            "",
        )

    return parent_value


def nested_task_records(task):
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
            nested = find_list(
                value,
                (
                    "subtasks",
                    "tasks",
                    "items",
                    "results",
                    "data",
                ),
            )

            result.extend(
                item
                for item in nested
                if isinstance(item, dict)
            )

    return result


def flatten_nested_tasks(tasks):
    result = []
    seen_ids = set()

    def append_task(task, parent=None):
        current = dict(task)

        if parent is not None:
            if not task_parent_id(current):
                current["parentId"] = task_id(parent)

            if not task_project_id(current):
                current["projectId"] = task_project_id(parent)

            if not current.get("project"):
                current["project"] = parent.get("project", "")

        current_id = task_id(current)

        if current_id != "":
            key = str(current_id)

            if key in seen_ids:
                return

            seen_ids.add(key)

        result.append(current)

        for child in nested_task_records(current):
            append_task(child, current)

    for task in tasks:
        append_task(task)

    return result


def safe(value):
    return html.escape(
        str(value or ""),
        quote=True,
    )


def write_json(filename, data):
    with (PUBLIC_DIR / filename).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def write_csv(tasks, projects_by_id):
    fields = [
        "id",
        "parent_id",
        "project_id",
        "project",
        "title",
        "status",
        "status_id",
        "is_completed",
        "overdue",
        "due_date",
        "created_at",
        "completed_at",
    ]

    with (PUBLIC_DIR / "weeek_tasks.csv").open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for task in tasks:
            writer.writerow(
                {
                    "id": task_id(task),
                    "parent_id": task_parent_id(task),
                    "project_id": task_project_id(task),
                    "project": task_project_name(
                        task,
                        projects_by_id,
                    ),
                    "title": task_title(task),
                    "status": task_status(task),
                    "status_id": task_status_id(task),
                    "is_completed": (
                        "Да"
                        if task_is_completed(task)
                        else "Нет"
                    ),
                    "overdue": (
                        "Да"
                        if task_overdue(task)
                        else "Нет"
                    ),
                    "due_date": task_due_date(task),
                    "created_at": first(
                        task,
                        (
                            "createdAt",
                            "created_at",
                        ),
                        "",
                    ),
                    "completed_at": first(
                        task,
                        (
                            "completedAt",
                            "completed_at",
                        ),
                        "",
                    ),
                }
            )


def make_html(tasks, projects):
    projects_by_id = {
        str(project.get("id")): project
        for project in projects
        if project.get("id") is not None
    }

    completed_count = sum(
        task_is_completed(task)
        for task in tasks
    )

    overdue_count = sum(
        task_overdue(task)
        and not task_is_completed(task)
        for task in tasks
    )

    not_started_count = sum(
        not task_is_completed(task)
        and not task_overdue(task)
        for task in tasks
    )

    status_counts = Counter(
        task_status(task)
        for task in tasks
    )

    project_counts = Counter(
        task_project_name(task, projects_by_id)
        for task in tasks
    )

    task_rows = []

    for task in tasks:
        title = task_title(task)

        if task_parent_id(task):
            title = "↳ " + title

        task_rows.append(
            "<tr>"
            f"<td>{safe(task_id(task))}</td>"
            f"<td>{safe(task_project_name(task, projects_by_id))}</td>"
            f"<td>{safe(title)}</td>"
            f"<td>{safe(task_status(task))}</td>"
            f"<td>{safe(task_due_date(task))}</td>"
            "</tr>"
        )

    status_rows = "".join(
        (
            "<tr>"
            f"<td>{safe(status)}</td>"
            f"<td>{count}</td>"
            "</tr>"
        )
        for status, count in status_counts.most_common()
    )

    project_rows = "".join(
        (
            "<tr>"
            f"<td>{safe(project)}</td>"
            f"<td>{count}</td>"
            "</tr>"
        )
        for project, count in project_counts.most_common()
    )

    task_rows_html = "".join(task_rows)

    updated_at = datetime.now().strftime(
        "%d.%m.%Y %H:%M"
    )

    parts = [
        "<!doctype html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8">',
        (
            '<meta name="viewport" '
            'content="width=device-width, initial-scale=1">'
        ),
        (
            '<meta http-equiv="Cache-Control" '
            'content="no-cache, no-store, must-revalidate">'
        ),
        (
            '<meta http-equiv="Pragma" content="no-cache">'
        ),
        (
            '<meta http-equiv="Expires" content="0">'
        ),
        "<title>Панель задач Weeek</title>",
        "<style>",
        "* { box-sizing: border-box; }",
        (
            "body { margin: 0; background: #f4f6f8; "
            "color: #202124; font-family: Arial, sans-serif; }"
        ),
        (
            "main { width: min(1400px, 100%); margin: 0 auto; "
            "padding: 24px; }"
        ),
        ".updated { margin-bottom: 24px; color: #5f6368; }",
        (
            ".cards { display: grid; "
            "grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); "
            "gap: 12px; }"
        ),
        (
            ".card, .panel { padding: 18px; background: white; "
            "border-radius: 12px; "
            "box-shadow: 0 2px 8px rgba(0, 0, 0, .08); }"
        ),
        (
            ".number { display: block; margin-bottom: 6px; "
            "font-size: 30px; font-weight: bold; }"
        ),
        ".label { color: #5f6368; }",
        ".panel { margin-top: 20px; }",
        ".table-wrapper { overflow-x: auto; }",
        (
            "table { width: 100%; min-width: 700px; "
            "border-collapse: collapse; }"
        ),
        (
            "th, td { padding: 11px; "
            "border-bottom: 1px solid #e5e7eb; "
            "text-align: left; vertical-align: top; }"
        ),
        "th { background: #eef1f4; }",
        "</style>",
        "</head>",
        "<body>",
        "<main>",
        "<h1>Панель задач Weeek</h1>",
        (
            '<div class="updated">Данные обновлены: '
            + safe(updated_at)
            + "</div>"
        ),
        '<section class="cards">',
        (
            '<div class="card"><span class="number">'
            + str(len(tasks))
            + '</span><span class="label">'
            "Всего задач и подзадач</span></div>"
        ),
        (
            '<div class="card"><span class="number">'
            + str(len(projects))
            + '</span><span class="label">Проектов</span></div>'
        ),
        (
            '<div class="card"><span class="number">'
            + str(completed_count)
            + '</span><span class="label">Выполнено</span></div>'
        ),
        (
            '<div class="card"><span class="number">'
            + str(overdue_count)
            + '</span><span class="label">Просрочено</span></div>'
        ),
        (
            '<div class="card"><span class="number">'
            + str(not_started_count)
            + '</span><span class="label">Не начато</span></div>"
        ),
        "</section>",
        '<section class="panel">',
        "<h2>Задачи по статусам</h2>",
        "<table>",
        "<thead><tr><th>Статус</th><th>Количество</th></tr></thead>",
        "<tbody>",
        status_rows,
        "</tbody>",
        "</table>",
        "</section>",
        '<section class="panel">',
        "<h2>Задачи по проектам</h2>",
        "<table>",
        "<thead><tr><th>Проект</th><th>Количество</th></tr></thead>",
        "<tbody>",
        project_rows,
        "</tbody>",
        "</table>",
        "</section>",
        '<section class="panel">',
        "<h2>Все задачи</h2>",
        '<div class="table-wrapper">',
        "<table>",
        (
            "<thead><tr><th>ID</th><th>Проект</th>"
            "<th>Название</th><th>Статус</th><th>Срок</th></tr></thead>"
        ),
        "<tbody>",
        task_rows_html,
        "</tbody>",
        "</table>",
        "</div>",
        "</section>",
        "</main>",
        "</body>",
        "</html>",
    ]

    with (PUBLIC_DIR / "index.html").open(
        "w",
        encoding="utf-8",
    ) as file:
        file.write("\n".join(parts))


def main():
    projects = load_projects()
    raw_tasks = load_tasks()
    tasks = flatten_nested_tasks(raw_tasks)

    projects_by_id = {
        str(project.get("id")): project
        for project in projects
        if project.get("id") is not None
    }

    write_json("weeek_projects.json", projects)
    write_json("weeek_raw_tasks.json", raw_tasks)
    write_json("weeek_tasks.json", tasks)

    write_csv(tasks, projects_by_id)
    make_html(tasks, projects)

    task_213 = next(
        (
            task
            for task in tasks
            if str(task_id(task)) == "213"
        ),
        None,
    )

    print(f"Проектов получено: {len(projects)}")
    print(f"Задач API получено: {len(raw_tasks)}")
    print(f"Всего задач после обработки: {len(tasks)}")
    print(
        "Выполнено: "
        + str(
            sum(
                task_is_completed(task)
                for task in tasks
            )
        )
    )

    if task_213:
        print(
            "Задача 213: "
            f"status={task_status(task_213)!r}, "
            f"isCompleted={task_is_completed(task_213)}"
        )


if __name__ == "__main__":
    main()
