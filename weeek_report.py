import csv
import html
import json
import os
from collections import Counter, defaultdict
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

    for key in ("tasks", "projects", "items", "results", "data"):
        value = payload.get(key)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            for nested_key in ("tasks", "projects", "items", "results"):
                nested_value = value.get(nested_key)

                if isinstance(nested_value, list):
                    return nested_value

    return []


def get_all(path):
    result = []
    offset = 0
    known_ids = set()

    while True:
        payload = api_get(
            path,
            {
                "offset": offset,
                "per_page": PER_PAGE,
            },
        )

        page = extract_items(payload)

        if not page:
            break

        new_items = 0

        for item in page:
            if not isinstance(item, dict):
                continue

            item_id = item.get("id")

            if item_id is not None:
                item_key = str(item_id)

                if item_key in known_ids:
                    continue

                known_ids.add(item_key)

            result.append(item)
            new_items += 1

        if len(page) < PER_PAGE or new_items == 0:
            break

        offset += len(page)

    return result


def get_tasks():
    for endpoint in ("/tm/tasks", "/tasks"):
        try:
            return get_all(endpoint)
        except requests.HTTPError:
            continue

    raise RuntimeError("Не удалось получить задачи Weeek")


def get_projects():
    for endpoint in ("/tm/projects", "/projects"):
        try:
            return get_all(endpoint)
        except requests.HTTPError:
            continue

    raise RuntimeError("Не удалось получить проекты Weeek")


def value_from(item, keys, default=""):
    for key in keys:
        value = item.get(key)

        if value is not None and value != "":
            return value

    return default


def text_value(value, default=""):
    if isinstance(value, dict):
        return str(
            value_from(
                value,
                ("name", "title", "label", "text", "id"),
                default,
            )
        )

    if value is None or value == "":
        return default

    return str(value)


def task_title(task):
    return text_value(
        value_from(task, ("title", "name", "text"), "Без названия")
    )


def task_project_id(task):
    project = task.get("project")

    if isinstance(project, dict):
        return value_from(project, ("id", "projectId"), "")

    return value_from(task, ("projectId", "project_id"), "")


def task_project_name(task, projects_by_id):
    project = task.get("project")

    if isinstance(project, dict):
        name = value_from(project, ("name", "title", "label"), "")

        if name:
            return str(name)

    project_id = task_project_id(task)

    if project_id != "":
        project = projects_by_id.get(str(project_id))

        if project:
            return text_value(project, "Без проекта")

    return "Без проекта"


def task_status(task):
    return text_value(
        value_from(task, ("status", "state", "column"), "Не указан"),
        "Не указан",
    )


def task_status_id(task):
    status = task.get("status")

    if isinstance(status, dict):
        return value_from(status, ("id", "statusId"), "")

    return value_from(
        task,
        ("statusId", "status_id", "stateId", "columnId"),
        "",
    )


def task_is_completed(task):
    value = value_from(
        task,
        ("isCompleted", "is_completed", "completed"),
        False,
    )

    if isinstance(value, bool):
        return value

    if isinstance(value, int):
        return value == 1

    return str(value).lower() in {
        "true",
        "1",
        "yes",
        "да",
    }


def task_due_date(task):
    return value_from(
        task,
        ("dueDate", "due_date", "deadline", "date"),
        "",
    )


def task_overdue(task):
    value = value_from(
        task,
        ("overdue", "overdueDays", "overdue_days"),
        0,
    )

    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def task_is_not_started(task):
    return not task_is_completed(task) and not task_overdue(task)


def task_priority(task):
    return text_value(
        value_from(task, ("priority", "priorityId"), ""),
        "",
    )


def task_assignees(task):
    values = value_from(
        task,
        ("assignees", "members", "users", "responsible"),
        [],
    )

    if not isinstance(values, list):
        values = [values] if values else []

    return ", ".join(text_value(value, str(value)) for value in values)


def task_description(task):
    return value_from(
        task,
        ("description", "content", "details"),
        "",
    )


def safe(value):
    return html.escape(str(value or ""), quote=True)


def write_json(filename, data):
    with (PUBLIC_DIR / filename).open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def write_csv(tasks, projects_by_id):
    fields = [
        "id",
        "project_id",
        "project",
        "title",
        "status_id",
        "status",
        "is_completed",
        "overdue",
        "due_date",
        "priority",
        "assignees",
        "description",
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
                    "id": task.get("id", ""),
                    "project_id": task_project_id(task),
                    "project": task_project_name(task, projects_by_id),
                    "title": task_title(task),
                    "status_id": task_status_id(task),
                    "status": task_status(task),
                    "is_completed": (
                        "Да" if task_is_completed(task) else "Нет"
                    ),
                    "overdue": (
                        "Да" if task_overdue(task) else "Нет"
                    ),
                    "due_date": task_due_date(task),
                    "priority": task_priority(task),
                    "assignees": task_assignees(task),
                    "description": task_description(task),
                    "created_at": value_from(
                        task,
                        ("createdAt", "created_at"),
                        "",
                    ),
                    "completed_at": value_from(
                        task,
                        ("completedAt", "completed_at"),
                        "",
                    ),
                }
            )


def make_task_rows(tasks, projects_by_id):
    rows = []

    for task in tasks:
        rows.append(
            "<tr>"
            f"<td>{safe(task.get('id', ''))}</td>"
            f"<td>{safe(task_project_name(task, projects_by_id))}</td>"
            f"<td>{safe(task_title(task))}</td>"
            f"<td>{safe(task_status(task))}</td>"
            f"<td>{safe(task_due_date(task))}</td>"
            "</tr>"
        )

    return "".join(rows)


def make_summary_rows(counter, total):
    rows = []

    for name, count in counter.most_common():
        percent = (count / total * 100) if total else 0

        rows.append(
            "<tr>"
            f"<td>{safe(name)}</td>"
            f"<td>{count}</td>"
            f"<td>{percent:.1f}%</td>"
            "</tr>"
        )

    return "".join(rows)


def make_project_rows(counter):
    rows = []

    for name, count in counter.most_common():
        rows.append(
            "<tr>"
            f"<td>{safe(name)}</td>"
            f"<td>{count}</td>"
            "</tr>"
        )

    return "".join(rows)


def make_html(tasks, projects):
    projects_by_id = {
        str(project.get("id")): project
        for project in projects
        if project.get("id") is not None
    }

    completed_count = sum(task_is_completed(task) for task in tasks)
    overdue_count = sum(
        task_overdue(task) and not task_is_completed(task)
        for task in tasks
    )
    not_started_count = sum(
        task_is_not_started(task)
        for task in tasks
    )

    status_counter = Counter(task_status(task) for task in tasks)

    project_counter = Counter(
        task_project_name(task, projects_by_id)
        for task in tasks
    )

    task_rows = make_task_rows(tasks, projects_by_id)
    status_rows = make_summary_rows(status_counter, len(tasks))
    project_rows = make_project_rows(project_counter)

    updated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    html_document = f"""<!doctype html>
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
      color: #202124;
      background: #f4f6f8;
      font-family: Arial, sans-serif;
    }}

    main {{
      width: min(1400px, 100%);
      margin: 0 auto;
      padding: 24px;
    }}

    h1 {{
      margin: 0 0 8px;
    }}

    h2 {{
      margin-top: 30px;
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

    .card {{
      padding: 18px;
      background: #fff;
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
      margin-top: 18px;
      padding: 18px;
      background: #fff;
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, .08);
    }}

    .table-wrapper {{
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      min-width: 650px;
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
        <span class="label">Всего задач</span>
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
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Статус</th>
              <th>Количество</th>
              <th>Процент</th>
            </tr>
          </thead>
          <tbody>
            {status_rows}
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>Задачи по проектам</h2>
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Проект</th>
              <th>Количество задач</th>
            </tr>
          </thead>
          <tbody>
            {project_rows}
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel">
      <h2>Все задачи</h2>
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>ID</th>
              <th>Проект</th>
              <th>Задача</th>
              <th>Статус</th>
              <th>Срок</th>
            </tr>
          </thead>
          <tbody>
            {task_rows}
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
        file.write(html_document)


def main():
    projects = get_projects()
    tasks = get_tasks()

    projects_by_id = {
        str(project.get("id")): project
        for project in projects
        if project.get("id") is not None
    }

    write_json("weeek_projects.json", projects)
    write_json("weeek_tasks.json", tasks)
    write_csv(tasks, projects_by_id)
    make_html(tasks, projects)

    print(f"Получено задач: {len(tasks)}")
    print(f"Выполнено: {sum(task_is_completed(task) for task in tasks)}")
    print(
        "Просрочено: "
        + str(
            sum(
                task_overdue(task) and not task_is_completed(task)
                for task in tasks
            )
        )
    )


if __name__ == "__main__":
    main()
