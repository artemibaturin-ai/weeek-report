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

PER_PAGE = 100


def api_get(path, params=None):
    response = requests.get(
        f"{API_URL}{path}",
        headers=HEADERS,
        params=params or {},
        timeout=60,
    )
    response.raise_for_status()
    return response.json()


def extract_items(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in ("tasks", "projects", "items", "results"):
        value = payload.get(key)

        if isinstance(value, list):
            return value

    data = payload.get("data")

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        return extract_items(data)

    return []


def load_all(path):
    all_items = []
    seen_ids = set()

    for page in range(1, 100):
        payload = api_get(
            path,
            {
                "page": page,
                "limit": PER_PAGE,
            },
        )

        items = extract_items(payload)

        if not items:
            break

        new_count = 0

        for item in items:
            if not isinstance(item, dict):
                continue

            item_id = item.get("id")

            if item_id is not None:
                key = str(item_id)

                if key in seen_ids:
                    continue

                seen_ids.add(key)

            all_items.append(item)
            new_count += 1

        if new_count == 0 or len(items) < PER_PAGE:
            break

    return all_items


def get_tasks():
    errors = []

    for path in ("/tm/tasks", "/tasks"):
        try:
            return load_all(path)
        except requests.HTTPError as error:
            errors.append(str(error))

    raise RuntimeError(
        "Не удалось получить задачи Weeek: "
        + " | ".join(errors)
    )


def get_projects():
    errors = []

    for path in ("/tm/projects", "/projects"):
        try:
            return load_all(path)
        except requests.HTTPError as error:
            errors.append(str(error))

    raise RuntimeError(
        "Не удалось получить проекты Weeek: "
        + " | ".join(errors)
    )


def value(item, keys, default=""):
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]

    return default


def text(value_to_convert, default=""):
    if isinstance(value_to_convert, dict):
        return str(
            value(
                value_to_convert,
                ("name", "title", "label", "text", "id"),
                default,
            )
        )

    if value_to_convert in (None, ""):
        return default

    return str(value_to_convert)


def task_id(task):
    return value(task, ("id", "taskId", "task_id"), "")


def task_title(task):
    return text(
        value(task, ("title", "name", "text"), "Без названия"),
        "Без названия",
    )


def task_project_id(task):
    return value(task, ("projectId", "project_id"), "")


def task_project_name(task, projects_by_id):
    project_value = task.get("project")

    if isinstance(project_value, str) and project_value:
        return project_value

    if isinstance(project_value, dict):
        return text(project_value, "Без проекта")

    project_id = task_project_id(task)

    if project_id != "":
        project = projects_by_id.get(str(project_id))

        if project:
            return text(project, "Без проекта")

    return "Без проекта"


def task_status(task):
    status_value = task.get("status")

    if isinstance(status_value, str) and status_value:
        return status_value

    if isinstance(status_value, dict):
        return text(status_value, "Не указан")

    return text(
        value(
            task,
            ("statusName", "status_name", "state", "column"),
            "",
        ),
        "Не указан",
    )


def task_is_completed(task):
    completed = value(
        task,
        ("isCompleted", "is_completed", "completed"),
        False,
    )

    if isinstance(completed, bool):
        return completed

    if isinstance(completed, int):
        return completed == 1

    if isinstance(completed, str):
        return completed.lower() in {
            "true",
            "1",
            "yes",
            "да",
        }

    return task_status(task).lower() in {
        "выполнено",
        "завершено",
        "готово",
        "done",
        "completed",
        "complete",
    }


def task_overdue(task):
    overdue = value(
        task,
        ("overdue", "overdueDays", "overdue_days"),
        0,
    )

    try:
        return int(overdue) > 0
    except (TypeError, ValueError):
        return False


def task_due_date(task):
    return value(
        task,
        ("dueDate", "due_date", "deadline", "date"),
        "",
    )


def task_parent_id(task):
    return value(
        task,
        (
            "parentId",
            "parent_id",
            "parentTaskId",
            "parent_task_id",
        ),
        "",
    )


def nested_tasks(task):
    result = []

    for key in ("subtasks", "children", "childTasks", "child_tasks"):
        nested = task.get(key)

        if isinstance(nested, list):
            result.extend(
                item
                for item in nested
                if isinstance(item, dict)
            )

    return result


def flatten_tasks(tasks):
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

        for child in nested_tasks(current):
            append_task(child, current)

    for task in tasks:
        append_task(task)

    return result


def safe(value_to_escape):
    return html.escape(
        str(value_to_escape or ""),
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
        "project_id",
        "project",
        "title",
        "status",
        "is_completed",
        "overdue",
        "due_date",
        "parent_id",
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
                    "parent_id": task_parent_id(task),
                    "created_at": value(
                        task,
                        ("createdAt", "created_at"),
                        "",
                    ),
                    "completed_at": value(
                        task,
                        ("completedAt", "completed_at"),
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
        "<tr>"
        f"<td>{safe(name)}</td>"
        f"<td>{count}</td>"
        "</tr>"
        for name, count in status_counts.most_common()
    )

    project_rows = "".join(
        "<tr>"
        f"<td>{safe(name)}</td>"
        f"<td>{count}</td>"
        "</tr>"
        for name, count in project_counts.most_common()
    )

    task_rows_html = "".join(task_rows)

    updated_at = datetime.now().strftime(
        "%d.%m.%Y %H:%M"
    )

    document = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
  <meta http-equiv="Pragma" content="no-cache">
  <meta http-equiv="Expires" content="0">
  <title>Панель задач Weeek</title>
  <style>
    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: #f4f6f8;
      color: #202124;
      font-family: Arial, sans-serif;
    }}

    main {{
      width: min(1400px, 100%);
      margin: 0 auto;
      padding: 24px;
    }}

    .updated {{
      margin-bottom: 24px;
      color: #5f6368;
    }}

    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
      gap: 12px;
    }}

    .card,
    .panel {{
      padding: 18px;
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, .08);
    }}

    .number {{
      display: block;
      margin-bottom: 6px;
      font-size: 30px;
      font-weight: bold;
    }}

    .label {{
      color: #5f6368;
    }}

    .panel {{
      margin-top: 20px;
    }}

    .table-wrapper {{
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      min-width: 700px;
      border-collapse: collapse;
    }}

    th,
    td {{
      padding: 11px;
      border-bottom: 1px solid #e5e7eb;
      text-align: left;
      vertical-align: top;
    }}

    th {{
      background: #eef1f4;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Панель задач Weeek</h1>

    <div class="updated">
      Данные обновлены: {safe(updated_at)}
    </div>

    <section class="cards">
      <div class="card">
        <span class="number">{len(tasks)}</span>
        <span class="label">Всего задач и подзадач</span>
      </div>

      <div class="card">
        <span class="number">{len(projects)}</span>
        <span class="label">Проектов</span>
      </div>

      <div class="card">
        <span class="number">{completed_count}</span>
        <span class="label">Выполнено</span>
      </div>

      <div class="card">
        <span class="number">{overdue_count}</span>
        <span class="label">Просрочено</span>
      </div>

      <div class="card">
        <span class="number">{not_started_count}</span>
        <span class="label">Не начато</span>
      </div>
    </section>

    <section class="panel">
      <h2>Задачи по статусам</h2>
      <table>
        <thead>
          <tr>
            <th>Статус</th>
            <th>Количество</th>
          </tr>
        </thead>
        <tbody>
          {status_rows}
        </tbody>
      </table>
    </section>

    <section class="panel">
      <h2>Задачи по проектам</h2>
      <table>
        <thead>
          <tr>
            <th>Проект</th>
            <th>Количество</th>
          </tr>
        </thead>
        <tbody>
          {project_rows}
        </tbody>
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
          <tbody>
            {task_rows_html}
          </tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>
"""

    with (PUBLIC_DIR / "index.html").open(
        "w",
        encoding="utf-8",
    ) as file:
        file.write(document)


def main():
    projects = get_projects()
    raw_tasks = get_tasks()
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


if __name__ == "__main__":
    main()
