import csv
import html
import json
import os
from collections import Counter
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


def request_json(path, params):
    response = requests.get(
        f"{API_URL}{path}",
        headers=HEADERS,
        params=params,
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def find_records(payload, kind):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    names = (
        ("tasks", "items", "results", "data")
        if kind == "tasks"
        else ("projects", "items", "results", "data")
    )

    for name in names:
        value = payload.get(name)

        if isinstance(value, list):
            return value

    for name in names:
        value = payload.get(name)

        if isinstance(value, dict):
            nested = find_records(value, kind)

            if nested:
                return nested

    return []


def load_collection(path, kind):
    result = []
    seen_ids = set()

    for offset in range(0, MAX_PAGES * PAGE_SIZE, PAGE_SIZE):
        payload = request_json(
            path,
            {
                "limit": PAGE_SIZE,
                "offset": offset,
            },
        )

        current = find_records(payload, kind)

        if not current:
            break

        added = 0

        for item in current:
            if not isinstance(item, dict):
                continue

            item_id = item.get("id")

            if item_id is not None:
                key = str(item_id)

                if key in seen_ids:
                    continue

                seen_ids.add(key)

            result.append(item)
            added += 1

        if added == 0:
            break

        if len(current) < PAGE_SIZE:
            break

    return result


def load_tasks():
    errors = []

    for path in ("/tm/tasks", "/tasks"):
        try:
            return load_collection(path, "tasks")
        except requests.HTTPError as error:
            errors.append(f"{path}: {error}")

    raise RuntimeError(
        "Ошибка загрузки задач: "
        + " | ".join(errors)
    )


def load_projects():
    errors = []

    for path in ("/tm/projects", "/projects"):
        try:
            return load_collection(path, "projects")
        except requests.HTTPError as error:
            errors.append(f"{path}: {error}")

    raise RuntimeError(
        "Ошибка загрузки проектов: "
        + " | ".join(errors)
    )


def first(item, keys, default=""):
    if not isinstance(item, dict):
        return default

    for key in keys:
        value = item.get(key)

        if value is not None and value != "":
            return value

    return default


def text(value, default=""):
    if isinstance(value, dict):
        return str(
            first(
                value,
                ("name", "title", "label", "text", "id"),
                default,
            )
        )

    if value is None or value == "":
        return default

    return str(value)


def task_id(task):
    return first(task, ("id", "taskId", "task_id"), "")


def task_title(task):
    return text(
        first(task, ("title", "name", "text"), "Без названия"),
        "Без названия",
    )


def task_project_id(task):
    project = task.get("project")

    if isinstance(project, dict):
        return first(project, ("id", "projectId"), "")

    return first(task, ("projectId", "project_id"), "")


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

    return text(
        first(
            task,
            ("statusName", "status_name", "state", "column"),
            "",
        ),
        "Не указан",
    )


def task_is_completed(task):
    value = first(
        task,
        ("isCompleted", "is_completed", "completed"),
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
        ("overdue", "overdueDays", "overdue_days"),
        0,
    )

    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def task_due_date(task):
    return first(
        task,
        ("dueDate", "due_date", "deadline", "date"),
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
        return first(value, ("id", "taskId"), "")

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
                item for item in value
                if isinstance(item, dict)
            )

        elif isinstance(value, dict):
            nested = find_records(value, "tasks")

            result.extend(
                item for item in nested
                if isinstance(item, dict)
            )

    return result


def flatten_tasks(tasks):
    result = []
    seen_ids = set()

    def add_task(task, parent=None):
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

        for child in nested_tasks(current):
            add_task(child, current)

    for task in tasks:
        add_task(task)

    return result


def safe(value):
    return html.escape(str(value or ""), quote=True)


def write_json(filename, data):
    (PUBLIC_DIR / filename).write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def write_csv(tasks, projects_by_id):
    fields = [
        "id",
        "parent_id",
        "project_id",
        "project",
        "title",
        "status",
        "is_completed",
        "overdue",
        "due_date",
    ]

    with (PUBLIC_DIR / "weeek_tasks.csv").open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fields,
        )
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
                }
            )


def make_html(tasks, projects):
    projects_by_id = {
        str(project.get("id")): project
        for project in projects
        if project.get("id") is not None
    }

    completed = sum(
        task_is_completed(task)
        for task in tasks
    )

    overdue = sum(
        task_overdue(task)
        and not task_is_completed(task)
        for task in tasks
    )

    not_started = sum(
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

    status_rows = "".join(
        "<tr><td>"
        + safe(status)
        + "</td><td>"
        + str(count)
        + "</td></tr>"
        for status, count in status_counts.most_common()
    )

    project_rows = "".join(
        "<tr><td>"
        + safe(project)
        + "</td><td>"
        + str(count)
        + "</td></tr>"
        for project, count in project_counts.most_common()
    )

    task_rows = []

    for task in tasks:
        title = task_title(task)

        if task_parent_id(task):
            title = "↳ " + title

        task_rows.append(
            "<tr><td>"
            + safe(task_id(task))
            + "</td><td>"
            + safe(task_project_name(task, projects_by_id))
            + "</td><td>"
            + safe(title)
            + "</td><td>"
            + safe(task_status(task))
            + "</td><td>"
            + safe(task_due_date(task))
            + "</td></tr>"
        )

    html_document = """
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Панель задач Weeek</title>
<style>
* { box-sizing: border-box; }
body {
  margin: 0;
  background: #f4f6f8;
  color: #202124;
  font-family: Arial, sans-serif;
}
main {
  width: min(1400px, 100%);
  margin: 0 auto;
  padding: 24px;
}
.cards {
  display: grid;
  grid-template-columns:
    repeat(auto-fit, minmax(160px, 1fr));
  gap: 12px;
}
.card, .panel {
  padding: 18px;
  margin-top: 18px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0,0,0,.08);
}
.number {
  display: block;
  font-size: 30px;
  font-weight: bold;
}
.label {
  color: #5f6368;
}
.table-wrapper {
  overflow-x: auto;
}
table {
  width: 100%;
  min-width: 700px;
  border-collapse: collapse;
}
th, td {
  padding: 10px;
  border-bottom: 1px solid #e5e7eb;
  text-align: left;
  vertical-align: top;
}
th {
  background: #eef1f4;
}
</style>
</head>
<body>
<main>
<h1>Панель задач Weeek</h1>
<p>Данные обновлены автоматически</p>

<section class="cards">
<div class="card">
<span class="number">__TOTAL__</span>
<span class="label">Всего задач и подзадач</span>
</div>
<div class="card">
<span class="number">__PROJECTS__</span>
<span class="label">Проектов</span>
</div>
<div class="card">
<span class="number">__COMPLETED__</span>
<span class="label">Выполнено</span>
</div>
<div class="card">
<span class="number">__OVERDUE__</span>
<span class="label">Просрочено</span>
</div>
<div class="card">
<span class="number">__NOT_STARTED__</span>
<span class="label">Не начато</span>
</div>
</section>

<section class="panel">
<h2>Задачи по статусам</h2>
<table>
<thead>
<tr><th>Статус</th><th>Количество</th></tr>
</thead>
<tbody>__STATUS_ROWS__</tbody>
</table>
</section>

<section class="panel">
<h2>Задачи по проектам</h2>
<table>
<thead>
<tr><th>Проект</th><th>Количество</th></tr>
</thead>
<tbody>__PROJECT_ROWS__</tbody>
</table>
</section>

<section class="panel">
<h2>Все задачи</h2>
<div class="table-wrapper">
<table>
<thead>
<tr>
<th>ID</th>
<th>Проект</th>
<th>Название</th>
<th>Статус</th>
<th>Срок</th>
</tr>
</thead>
<tbody>__TASK_ROWS__</tbody>
</table>
</div>
</section>
</main>
</body>
</html>
"""

    replacements = {
        "__TOTAL__": str(len(tasks)),
        "__PROJECTS__": str(len(projects)),
        "__COMPLETED__": str(completed),
        "__OVERDUE__": str(overdue),
        "__NOT_STARTED__": str(not_started),
        "__STATUS_ROWS__": status_rows,
        "__PROJECT_ROWS__": project_rows,
        "__TASK_ROWS__": "".join(task_rows),
    }

    for marker, replacement in replacements.items():
        html_document = html_document.replace(
            marker,
            replacement,
        )

    (PUBLIC_DIR / "index.html").write_text(
        html_document,
        encoding="utf-8",
    )


def main():
    projects = load_projects()
    raw_tasks = load_tasks()
    tasks = flatten_tasks(raw_tasks)

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

    if task_213 is not None:
        print(
            "Задача 213: "
            f"status={task_status(task_213)!r}, "
            f"isCompleted={task_is_completed(task_213)}"
        )


if __name__ == "__main__":
    main()
