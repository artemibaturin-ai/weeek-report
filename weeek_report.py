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


def extract_list(payload, names):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for name in names:
        value = payload.get(name)

        if isinstance(value, list):
            return value

        if isinstance(value, dict):
            nested = extract_list(value, names)

            if nested:
                return nested

    for value in payload.values():
        if isinstance(value, dict):
            nested = extract_list(value, names)

            if nested:
                return nested

    return []


def has_more(payload, page_length, offset):
    if not isinstance(payload, dict):
        return page_length >= PER_PAGE

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
            return offset + page_length < total

    total = payload.get("total")

    if isinstance(total, int):
        return offset + page_length < total

    return page_length >= PER_PAGE


def get_paginated(path, names, extra_params=None):
    result = []
    offset = 0
    seen_ids = set()

    while True:
        params = {
            "offset": offset,
            "per_page": PER_PAGE,
        }

        if extra_params:
            params.update(extra_params)

        payload = api_get(path, params)
        page = extract_list(payload, names)

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

            result.append(item)
            added += 1

        if added == 0:
            break

        if not has_more(payload, len(page), offset):
            break

        if len(page) < PER_PAGE:
            break

        offset += len(page)

    return result


def get_projects():
    errors = []

    for endpoint in ("/tm/projects", "/projects"):
        try:
            return get_paginated(
                endpoint,
                ("projects", "items", "results", "data"),
            )
        except requests.HTTPError as error:
            errors.append(str(error))

    raise RuntimeError(
        "Не удалось получить проекты Weeek: "
        + " | ".join(errors)
    )


def get_tasks():
    errors = []

    for endpoint in ("/tm/tasks", "/tasks"):
        try:
            return get_paginated(
                endpoint,
                ("tasks", "items", "results", "data"),
            )
        except requests.HTTPError as error:
            errors.append(str(error))

    raise RuntimeError(
        "Не удалось получить задачи Weeek: "
        + " | ".join(errors)
    )


def first_value(item, keys, default=""):
    if not isinstance(item, dict):
        return default

    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]

    return default


def text_value(value, default=""):
    if isinstance(value, dict):
        return str(
            first_value(
                value,
                ("name", "title", "label", "text", "id"),
                default,
            )
        )

    if value in (None, ""):
        return default

    return str(value)


def task_id(task):
    return first_value(task, ("id", "taskId", "task_id"), "")


def project_id(task):
    project = task.get("project")

    if isinstance(project, dict):
        return first_value(project, ("id", "projectId"), "")

    return first_value(
        task,
        ("projectId", "project_id"),
        "",
    )


def parent_id(task):
    parent = first_value(
        task,
        (
            "parentId",
            "parent_id",
            "parentTaskId",
            "parent_task_id",
        ),
        "",
    )

    if isinstance(parent, dict):
        return first_value(parent, ("id", "taskId"), "")

    return parent


def task_title(task):
    return text_value(
        first_value(
            task,
            ("title", "name", "text"),
            "Без названия",
        ),
        "Без названия",
    )


def task_status(task):
    return text_value(
        first_value(
            task,
            ("status", "state", "column"),
            "Не указан",
        ),
        "Не указан",
    )


def task_status_id(task):
    status = task.get("status")

    if isinstance(status, dict):
        return first_value(status, ("id", "statusId"), "")

    return first_value(
        task,
        ("statusId", "status_id", "stateId", "columnId"),
        "",
    )


def task_is_completed(task):
    value = first_value(
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
    return first_value(
        task,
        ("dueDate", "due_date", "deadline", "date"),
        "",
    )


def task_overdue(task):
    value = first_value(
        task,
        ("overdue", "overdueDays", "overdue_days"),
        0,
    )

    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def task_priority(task):
    return text_value(
        first_value(task, ("priority", "priorityId"), ""),
        "",
    )


def task_assignees(task):
    values = first_value(
        task,
        ("assignees", "members", "users", "responsible"),
        [],
    )

    if not isinstance(values, list):
        values = [values] if values else []

    return ", ".join(
        text_value(value, str(value))
        for value in values
    )


def task_description(task):
    return first_value(
        task,
        ("description", "content", "details"),
        "",
    )


def safe(value):
    return html.escape(str(value or ""), quote=True)


def collect_nested_subtasks(task):
    found = []

    for key in ("subtasks", "children", "childTasks", "child_tasks"):
        value = task.get(key)

        if isinstance(value, list):
            found.extend(
                item for item in value
                if isinstance(item, dict)
            )

        elif isinstance(value, dict):
            nested = extract_list(
                value,
                ("subtasks", "tasks", "items", "data"),
            )
            found.extend(
                item for item in nested
                if isinstance(item, dict)
            )

    return found


def get_subtasks_for_task(task):
    current_id = task_id(task)

    if current_id == "":
        return []

    endpoints = (
        f"/tm/tasks/{current_id}/subtasks",
        f"/tasks/{current_id}/subtasks",
        f"/tm/tasks/{current_id}/children",
        f"/tasks/{current_id}/children",
    )

    for endpoint in endpoints:
        try:
            return get_paginated(
                endpoint,
                ("subtasks", "tasks", "items", "results", "data"),
            )
        except requests.HTTPError:
            continue

    return []


def add_subtasks(tasks):
    result = []
    known_ids = set()

    def add_task(task, parent=None):
        if not isinstance(task, dict):
            return

        current = dict(task)
        current_id = task_id(current)

        if parent is not None and parent_id(current) == "":
            current["parentId"] = task_id(parent)

        current_id = task_id(current)

        if current_id != "":
            marker = str(current_id)

            if marker in known_ids:
                return

            known_ids.add(marker)

        result.append(current)

        nested = collect_nested_subtasks(current)

        if not nested:
            nested = get_subtasks_for_task(current)

        for child in nested:
            add_task(child, current)

    for task in tasks:
        add_task(task)

    return result


def project_name(task, projects_by_id):
    project = task.get("project")

    if isinstance(project, dict):
        name = first_value(
            project,
            ("name", "title", "label"),
            "",
        )

        if name:
            return str(name)

    current_project_id = project_id(task)

    if current_project_id != "":
        project_data = projects_by_id.get(str(current_project_id))

        if project_data:
            return text_value(project_data, "Без проекта")

    return "Без проекта"


def write_json(filename, data):
    with (PUBLIC_DIR / filename).open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def write_csv(tasks, projects_by_id):
    fields = [
        "id",
        "parent_id",
        "type",
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
            is_child = parent_id(task) != ""

            writer.writerow(
                {
                    "id": task_id(task),
                    "parent_id": parent_id(task),
                    "type": (
                        "Подзадача"
                        if is_child
                        else "Задача"
                    ),
                    "project_id": project_id(task),
                    "project": project_name(
                        task,
                        projects_by_id,
                    ),
                    "title": task_title(task),
                    "status_id": task_status_id(task),
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
                    "priority": task_priority(task),
                    "assignees": task_assignees(task),
                    "description": task_description(task),
                    "created_at": first_value(
                        task,
                        ("createdAt", "created_at"),
                        "",
                    ),
                    "completed_at": first_value(
                        task,
                        ("completedAt", "completed_at"),
                        "",
                    ),
                }
            )


def make_html(tasks, projects):
    projects_by_id = {
        str(item.get("id")): item
        for item in projects
        if item.get("id") is not None
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

    status_counter = Counter(
        task_status(task)
        for task in tasks
    )

    project_counter = Counter(
        project_name(task, projects_by_id)
        for task in tasks
    )

    rows = []

    for task in tasks:
        title = task_title(task)

        if parent_id(task) != "":
            title = "↳ " + title

        rows.append(
            "<tr>"
            f"<td>{safe(task_id(task))}</td>"
            f"<td>{safe(project_name(task, projects_by_id))}</td>"
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
        for name, count in status_counter.most_common()
    )

    project_rows = "".join(
        "<tr>"
        f"<td>{safe(name)}</td>"
        f"<td>{count}</td>"
        "</tr>"
        for name, count in project_counter.most_common()
    )

    if not rows:
        rows.append(
            '<tr><td colspan="5">Задачи не найдены</td></tr>'
        )

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
        <span class="number">{completed}</span>
        <span class="label">Выполнено</span>
      </div>

      <div class="card">
        <span class="number">{overdue}</span>
        <span class="label">Просрочено</span>
      </div>

      <div class="card">
        <span class="number">{not_started}</span>
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

    <section class="panel">
      <h2>Все задачи и подзадачи</h2>
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
            {"".join(rows)}
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
    parent_tasks = get_tasks()
    all_tasks = add_subtasks(parent_tasks)

    projects_by_id = {
        str(item.get("id")): item
        for item in projects
        if item.get("id") is not None
    }

    write_json("weeek_projects.json", projects)
    write_json("weeek_parent_tasks.json", parent_tasks)
    write_json("weeek_tasks.json", all_tasks)

    write_csv(all_tasks, projects_by_id)
    make_html(all_tasks, projects)

    parent_count = len(parent_tasks)
    subtask_count = len(all_tasks) - parent_count

    print(f"Проектов: {len(projects)}")
    print(f"Родительских задач: {parent_count}")
    print(f"Подзадач: {subtask_count}")
    print(f"Всего задач: {len(all_tasks)}")
    print(
        "Выполнено: "
        + str(
            sum(
                task_is_completed(task)
                for task in all_tasks
            )
        )
    )


if __name__ == "__main__":
    main()
