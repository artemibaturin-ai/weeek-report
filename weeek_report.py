import csv
import html
import json
import os
from datetime import datetime
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
PUBLIC_DIR.mkdir(parents=True, exist_ok=True)

TOKEN = os.environ.get("WEEEK_TOKEN")

if not TOKEN:
    raise RuntimeError("Не найден секрет WEEEK_TOKEN")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
}

API_URL = "https://api.weeek.net/public/v1"


def get_tasks():
    response = requests.get(
        f"{API_URL}/tm/tasks",
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()

    if isinstance(data, dict):
        return data.get("tasks", data.get("data", []))

    return data


def task_title(task):
    return task.get("title") or task.get("name") or task.get("text") or "Без названия"


def task_status(task):
    status = task.get("status")

    if isinstance(status, dict):
        return (
            status.get("name")
            or status.get("title")
            or str(status.get("id", "Не указан"))
        )

    return str(status or "Не указан")


def task_project(task):
    project = task.get("project")

    if isinstance(project, dict):
        return (
            project.get("name")
            or project.get("title")
            or str(project.get("id", "Без проекта"))
        )

    return str(project or "Без проекта")


def task_due_date(task):
    return (
        task.get("dueDate")
        or task.get("due_date")
        or task.get("deadline")
        or ""
    )


def is_completed(task):
    value = task.get("completed")

    if isinstance(value, bool):
        return value

    status = task_status(task).lower()

    return status in {
        "done",
        "completed",
        "complete",
        "выполнено",
        "завершено",
    }


def is_overdue(task):
    due_date = task_due_date(task)

    if not due_date or is_completed(task):
        return False

    try:
        date_value = datetime.strptime(
            str(due_date)[:10],
            "%Y-%m-%d",
        ).date()

        return date_value < datetime.now().date()
    except ValueError:
        return False


def safe(value):
    return html.escape(str(value or ""), quote=True)


def make_csv(tasks):
    path = PUBLIC_DIR / "weeek_tasks.csv"

    fields = [
        "title",
        "status",
        "project",
        "due_date",
        "completed",
        "overdue",
    ]

    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()

        for task in tasks:
            writer.writerow(
                {
                    "title": task_title(task),
                    "status": task_status(task),
                    "project": task_project(task),
                    "due_date": task_due_date(task),
                    "completed": "Да" if is_completed(task) else "Нет",
                    "overdue": "Да" if is_overdue(task) else "Нет",
                }
            )


def make_json(tasks):
    path = PUBLIC_DIR / "weeek_tasks.json"

    with path.open("w", encoding="utf-8") as file:
        json.dump(tasks, file, ensure_ascii=False, indent=2)


def make_html(tasks):
    updated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    total = len(tasks)
    completed = sum(is_completed(task) for task in tasks)
    overdue = sum(is_overdue(task) for task in tasks)
    not_completed = total - completed

    projects = {task_project(task) for task in tasks}

    rows = []

    for task in tasks:
        rows.append(
            "<tr>"
            f"<td>{safe(task_title(task))}</td>"
            f"<td>{safe(task_status(task))}</td>"
            f"<td>{safe(task_project(task))}</td>"
            f"<td>{safe(task_due_date(task))}</td>"
            "</tr>"
        )

    rows_html = "".join(rows)

    if rows_html:
        tasks_content = (
            '<div class="table-wrapper">'
            "<table>"
            "<thead>"
            "<tr>"
            "<th>Название</th>"
            "<th>Статус</th>"
            "<th>Проект</th>"
            "<th>Срок</th>"
            "</tr>"
            "</thead>"
            f"<tbody>{rows_html}</tbody>"
            "</table>"
            "</div>"
        )
    else:
        tasks_content = '<div class="empty">Задачи не найдены</div>'

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
      width: min(1200px, 100%);
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

    .card {{
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

    .table-wrapper {{
      overflow-x: auto;
      background: white;
      border-radius: 12px;
      box-shadow: 0 2px 8px rgba(0, 0, 0, .08);
    }}

    table {{
      width: 100%;
      min-width: 650px;
      border-collapse: collapse;
    }}

    th,
    td {{
      padding: 12px;
      border-bottom: 1px solid #e5e7eb;
      text-align: left;
      vertical-align: top;
    }}

    th {{
      background: #eef1f4;
    }}

    .empty {{
      padding: 24px;
      background: white;
      border-radius: 12px;
      color: #5f6368;
      text-align: center;
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
        <span class="number">{total}</span>
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
        <span class="number">{not_completed}</span>
        <span class="label">Не завершено</span>
      </div>
    </section>

    <h2>Задачи</h2>

    {tasks_content}
  </main>
</body>
</html>
"""

    path = PUBLIC_DIR / "index.html"

    with path.open("w", encoding="utf-8") as file:
        file.write(html_document)


def main():
    tasks = get_tasks()

    if not isinstance(tasks, list):
        raise RuntimeError("API Weeek вернул неожиданный формат данных")

    make_csv(tasks)
    make_json(tasks)
    make_html(tasks)

    print(f"Создано задач: {len(tasks)}")
    print(f"Создан файл: {PUBLIC_DIR / 'index.html'}")


if __name__ == "__main__":
    main()
