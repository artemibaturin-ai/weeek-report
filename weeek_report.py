import csv
import html
import json
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode

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
    payload = response.json()

    if isinstance(payload, dict):
        if isinstance(payload.get("data"), dict):
            return payload["data"]

        return payload

    return payload


def extract_items(payload, names):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for name in names:
        value = payload.get(name)

        if isinstance(value, list):
            return value

    data = payload.get("data")

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for name in names:
            value = data.get(name)

            if isinstance(value, list):
                return value

    return []


def extract_has_more(payload, current_count, offset):
    if not isinstance(payload, dict):
        return current_count >= PER_PAGE

    for key in ("hasMore", "has_more", "hasNext", "has_next"):
        if key in payload:
            return bool(payload[key])

    pagination = payload.get("pagination")

    if isinstance(pagination, dict):
        for key in ("hasMore", "has_more", "hasNext", "has_next"):
            if key in pagination:
                return bool(pagination[key])

        total = pagination.get("total")

        if isinstance(total, int):
            return offset + current_count < total

    total = payload.get("total")

    if isinstance(total, int):
        return offset + current_count < total

    return current_count >= PER_PAGE


def get_all(path, item_names):
    items = []
    offset = 0
    seen_ids = set()

    while True:
        params = {
            "offset": offset,
            "per_page": PER_PAGE,
        }

        payload = api_get(path, params)
        page = extract_items(payload, item_names)

        if not page:
            break

        added = 0

        for item in page:
            if not isinstance(item, dict):
                continue

            item_id = item.get("id")

            if item_id is not None:
                marker = str(item_id)

                if marker in seen_ids:
                    continue

                seen_ids.add(marker)

            items.append(item)
            added += 1

        if not extract_has_more(payload, len(page), offset):
            break

        if added == 0:
            break

        offset += len(page)

        if len(page) < PER_PAGE:
            break

    return items


def get_projects():
    candidates = (
        "/tm/projects",
        "/projects",
    )

    last_error = None

    for path in candidates:
        try:
            return get_all(
                path,
                ("projects", "items", "results"),
            )
        except requests.HTTPError as error:
            last_error = error

    if last_error:
        raise last_error

    return []


def get_tasks():
    candidates = (
        "/tm/tasks",
        "/tasks",
    )

    last_error = None

    for path in candidates:
        try:
            return get_all(
                path,
                ("tasks", "items", "results"),
            )
        except requests.HTTPError as error:
            last_error = error

    if last_error:
        raise last_error

    return []


def first_value(item, keys, default=""):
    for key in keys:
        value = item.get(key)

        if value is not None and value != "":
            return value

    return default


def object_name(value, default=""):
    if isinstance(value, dict):
        return str(
            first_value(
                value,
                ("name", "title", "label", "text", "id"),
                default,
            )
        )

    if value is None or value == "":
        return default

    return str(value)


def get_task_project_id(task):
    project = task.get("project")

    if isinstance(project, dict):
        return first_value(project, ("id", "projectId"))

    value = first_value(
        task,
        ("projectId", "project_id"),
        None,
    )

    if value is not None:
        return value

    return None


def get_task_project_name(task, projects_by_id):
    project = task.get("project")

    if isinstance(project, dict):
        name = first_value(
            project,
            ("name", "title", "label"),
            "",
        )

        if name:
            return str(name)

    project_id = get_task_project_id(task)

    if project_id is not None:
        project_data = projects_by_id.get(str(project_id))

        if project_data:
            return object_name(project_data, "Без проекта")

    return "Без проекта"


def get_status_name(task):
    status = first_value(
        task,
        ("status", "state", "column"),
        "",
    )

    return object_name(status, "Не указан")


def get_status_id(task):
    status = first_value(
        task,
        ("status", "state", "column"),
        None,
    )

    if isinstance(status, dict):
        return first_value(status, ("id", "statusId"), "")

    return first_value(
        task,
        ("statusId", "status_id", "stateId", "columnId"),
        status or "",
    )


def get_title(task):
    return str(
        first_value(
            task,
            ("title", "name", "text"),
            "Без названия",
        )
    )


def get_due_date(task):
    return first_value(
        task,
        (
            "dueDate",
            "due_date",
            "deadline",
            "date",
        ),
        "",
    )


def get_assignees(task):
    values = first_value(
        task,
        ("assignees", "members", "users", "responsible"),
        [],
    )

    if not isinstance(values, list):
        values = [values] if values else []

    result = []

    for value in values:
        result.append(object_name(value, str(value)))

    return ", ".join(result)


def get_priority(task):
    priority = first_value(
        task,
        ("priority", "priorityId"),
        "",
    )

    return object_name(priority, "")


def get_description(task):
    return first_value(
        task,
        ("description", "content", "details"),
        "",
    )


def is_completed(task):
    value = task.get("completed")

    if isinstance(value, bool):
        return value

    status = get_status_name(task).lower()

    return status in {
        "done",
        "completed",
        "complete",
        "finished",
        "выполнено",
        "завершено",
    }


def is_overdue(task):
    due_date = get_due_date(task)

    if not due_date or is_completed(task):
        return False

    text = str(due_date)[:10]

    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            parsed = datetime.strptime(text, pattern).date()
            return parsed < datetime.now().date()
        except ValueError:
            continue

    return False


def safe(value):
    return html.escape(str(value or ""), quote=True)


def write_json(filename, value):
    path = PUBLIC_DIR / filename

    with path.open("w", encoding="utf-8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)


def write_csv(tasks, projects_by_id):
    path = PUBLIC_DIR / "weeek_tasks.csv"

    fields = [
        "id",
        "title",
        "project_id",
        "project",
        "status_id",
        "status",
        "due_date",
        "priority",
        "assignees",
        "completed",
        "overdue",
        "description",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for task in tasks:
            writer.writerow(
                {
                    "id": task.get("id", ""),
                    "title": get_title(task),
                    "project_id": get_task_project_id(task) or "",
                    "project": get_task_project_name(
                        task,
                        projects_by_id,
                    ),
                    "status_id": get_status_id(task),
                    "status": get_status_name(task),
                    "due_date": get_due_date(task),
                    "priority": get_priority(task),
                    "assignees": get_assignees(task),
                    "completed": "Да" if is_completed(task) else "Нет",
                    "overdue": "Да" if is_overdue(task) else "Нет",
                    "description": get_description(task),
                }
            )


def make_project_cards(projects):
    cards = []

    for project in projects:
        project_id = project.get("id", "")
        project_name = object_name(project, "Без названия")
        project_status = object_name(
            first_value(project, ("status", "state"), ""),
            "",
        )

        cards.append(
            "<article class=\"project-card\">"
            f"<h3>{safe(project_name)}</h3>"
            f"<div>ID: {safe(project_id)}</div>"
            f"<div>Статус: {safe(project_status or 'Не указан')}</div>"
            "</article>"
        )

    return "".join(cards)


def make_status_rows(status_groups):
    rows = []

    for status, status_tasks in sorted(
        status_groups.items(),
        key=lambda pair: pair[0].lower(),
    ):
        rows.append(
            "<tr>"
            f"<td>{safe(status)}</td>"
            f"<td>{len(status_tasks)}</td>"
            "</tr>"
        )

    return "".join(rows)


def make_project_rows(project_groups):
    rows = []

    for project, project_tasks in sorted(
        project_groups.items(),
        key=lambda pair: pair[0].lower(),
    ):
        rows.append(
            "<tr>"
            f"<td>{safe(project)}</td>"
            f"<td>{len(project_tasks)}</td>"
            "</tr>"
        )

    return "".join(rows)


def make_task_rows(tasks, projects_by_id):
    rows = []

    for task in tasks:
        project_name = get_task_project_name(task, projects_by_id)
        status_name = get_status_name(task)
        title = get_title(task)
        due_date = get_due_date(task)
        priority = get_priority(task)
        assignees = get_assignees(task)

        rows.append(
            "<tr>"
            f"<td>{safe(title)}</td>"
            f"<td>{safe(project_name)}</td>"
            f"<td>{safe(status_name)}</td>"
            f"<td>{safe(due_date)}</td>"
            f"<td>{safe(priority)}</td>"
            f"<td>{safe(assignees)}</td>"
            "</tr>"
        )

    return "".join(rows)


def make_html(tasks, projects):
    projects_by_id = {
        str(project.get("id")): project
        for project in projects
        if project.get("id") is not None
    }

    status_groups = defaultdict(list)
    project_groups = defaultdict(list)

    for task in tasks:
        status_groups[get_status_name(task)].append(task)

        project_groups[
            get_task_project_name(task, projects_by_id)
        ].append(task)

    completed = sum(is_completed(task) for task in tasks)
    overdue = sum(is_overdue(task) for task in tasks)
    not_started = len(tasks) - completed
    updated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    project_cards = make_project_cards(projects)
    status_rows = make_status_rows(status_groups)
    project_rows = make_project_rows(project_groups)
    task_rows = make_task_rows(tasks, projects_by_id)

    if not project_cards:
        project_cards = (
            '<div class="empty">Проекты не найдены в API</div>'
        )

    if not task_rows:
        task_rows = (
            '<tr><td colspan="6">Задачи не найдены</td></tr>'
        )

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
      background: #f4f6f8;
      color: #202124;
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
      margin-top: 32px;
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
    .project-card,
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

    .projects {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}

    .project-card h3 {{
      margin-top: 0;
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 18px;
    }}

    .table-wrapper {{
      overflow-x: auto;
    }}

    table {{
      width: 100%;
      min-width: 600px;
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

    .empty {{
      padding: 18px;
      color: #5f6368;
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
        <span class="number">{completed}</span>
        <span class="label">Выполнено</span>
      </div>

      <div class="card">
        <span class="number">{overdue}</span>
        <span class="label">Просрочено</span>
      </div>

      <div class="card">
        <span class="number">{not_started}</span>
        <span class="label">Не завершено</span>
      </div>
    </section>

    <h2>Все проекты</h2>
    <section class="projects">
      {project_cards}
    </section>

    <div class="grid">
      <section class="panel">
        <h2>Задачи по статусам</h2>
        <div class="table-wrapper">
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
        </div>
      </section>

      <section class="panel">
        <h2>Задачи по проектам</h2>
        <div class="table-wrapper">
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
        </div>
      </section>
    </div>

    <section class="panel">
      <h2>Все задачи</h2>
      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Название</th>
              <th>Проект</th>
              <th>Статус</th>
              <th>Срок</th>
              <th>Приоритет</th>
              <th>Исполнители</th>
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

    path = PUBLIC_DIR / "index.html"

    with path.open("w", encoding="utf-8") as file:
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

    print(f"Получено проектов: {len(projects)}")
    print(f"Получено задач: {len(tasks)}")
    print(f"Создан файл: {PUBLIC_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
