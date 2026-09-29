import csv
import html
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TOKEN = os.environ.get("WEEEK_TOKEN")
BASE_URL = "https://api.weeek.net/public/v1"

if not TOKEN:
    print("Ошибка: секрет WEEEK_TOKEN не передан")
    sys.exit(1)


def api_get(path, params=None):
    query = f"?{urlencode(params)}" if params else ""
    url = BASE_URL + path + query

    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/json",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"Ошибка API: HTTP {error.code}")
        print(f"Адрес: {url}")
        print(body)
        sys.exit(1)

    except URLError as error:
        print(f"Ошибка соединения: {error.reason}")
        sys.exit(1)


def get_projects():
    result = api_get("/tm/projects")
    projects = result.get("projects", [])

    print(f"Найдено проектов: {len(projects)}")

    for project in projects:
        print(
            f"Проект {project.get('id')}: "
            f"{project.get('title') or project.get('name')}"
        )

    return projects


def get_tasks_for_project(project_id):
    all_tasks = []
    seen_ids = set()

    limit = 100
    offset = 0

    while True:
        params = {
            "projectId": project_id,
            "limit": limit,
            "offset": offset,
        }

        result = api_get("/tm/tasks", params)
        tasks = result.get("tasks", [])

        new_tasks = []

        for task in tasks:
            task_id = task.get("id")

            if task_id is None:
                continue

            if task_id not in seen_ids:
                seen_ids.add(task_id)
                new_tasks.append(task)

        all_tasks.extend(new_tasks)

        print(
            f"Проект {project_id}, offset {offset}: "
            f"получено {len(tasks)}, новых {len(new_tasks)}, "
            f"уникальных всего {len(all_tasks)}"
        )

        if not tasks:
            break

        if len(new_tasks) == 0:
            print(
                f"Проект {project_id}: API повторяет страницу, "
                "переход остановлен"
            )
            break

        if len(tasks) < limit:
            break

        offset += limit

        if offset > 100000:
            print("Остановлено после 100000 записей")
            break

    return all_tasks


def get_status(task):
    if task.get("isDeleted"):
        return "Удалено"

    if task.get("isCompleted"):
        return "Выполнено"

    if task.get("overdue", 0) > 0:
        return "Просрочено"

    if task.get("date") or task.get("dueDate"):
        return "Запланировано"

    return "Не начато"


def prepare_rows(tasks, project_names):
    rows = []

    for task in tasks:
        project_id = task.get("projectId")

        rows.append({
            "id": task.get("id", ""),
            "projectId": project_id or "",
            "project": project_names.get(project_id, "Без проекта"),
            "title": task.get("title", ""),
            "status": get_status(task),
            "isCompleted": task.get("isCompleted", False),
            "overdue": task.get("overdue", 0),
            "dueDate": task.get("dueDate") or "",
            "createdAt": task.get("createdAt") or "",
            "completedAt": task.get("completedAt") or "",
        })

    rows.sort(key=lambda row: int(row["id"]) if str(row["id"]).isdigit() else 0, reverse=True)
    return rows


def save_csv(rows):
    columns = [
        "id",
        "projectId",
        "project",
        "title",
        "status",
        "isCompleted",
        "overdue",
        "dueDate",
        "createdAt",
        "completedAt",
    ]

    with open("weeek_tasks.csv", "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def save_json(rows):
    with open("weeek_tasks.json", "w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)


def save_html(rows):
    status_counts = Counter(row["status"] for row in rows)
    project_counts = Counter(row["project"] for row in rows)

    status_order = [
        "Выполнено",
        "Просрочено",
        "Запланировано",
        "Не начато",
        "Удалено",
    ]

    status_labels = [
        status for status in status_order
        if status in status_counts
    ]

    for status in status_counts:
        if status not in status_labels:
            status_labels.append(status)

    status_values = [status_counts[label] for label in status_labels]
    project_labels = list(project_counts.keys())
    project_values = [project_counts[label] for label in project_labels]

    status_table = []

    for status in status_labels:
        count = status_counts[status]
        percent = round(count / len(rows) * 100, 1) if rows else 0

        status_table.append(
            "<tr>"
            f"<td>{html.escape(status)}</td>"
            f"<td>{count}</td>"
            f"<td>{percent}%</td>"
            "</tr>"
        )

    project_table = []

    for project in project_labels:
        project_table.append(
            "<tr>"
            f"<td>{html.escape(project)}</td>"
            f"<td>{project_counts[project]}</td>"
            "</tr>"
        )

    task_table = []

    for row in rows:
        task_table.append(
            "<tr>"
            f"<td>{row['id']}</td>"
            f"<td>{html.escape(row['project'])}</td>"
            f"<td>{html.escape(row['title'])}</td>"
            f"<td>{html.escape(row['status'])}</td>"
            f"<td>{html.escape(str(row['dueDate']))}</td>"
            "</tr>"
        )

    now = datetime.now(timezone.utc) + timedelta(hours=7)
    updated_at = now.strftime("%d.%m.%Y %H:%M")

    html_lines = [
        "<!DOCTYPE html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Панель задач Weeek</title>",
        '<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>',
        "<style>",
        "body { font-family: Arial, sans-serif; margin: 0; padding: 25px; background: #f5f7fa; color: #222; }",
        ".container { max-width: 1500px; margin: auto; }",
        ".updated { color: #667085; margin-bottom: 20px; }",
        ".cards { display: flex; flex-wrap: wrap; gap: 15px; margin: 20px 0; }",
        ".card { min-width: 150px; padding: 18px; border-radius: 10px; background: white; box-shadow: 0 2px 8px rgba(0,0,0,.05); }",
        ".card span { display: block; margin-top: 8px; font-size: 28px; font-weight: bold; }",
        ".grid { display: grid; grid-template-columns: 1fr 1fr; gap: 25px; }",
        ".panel { background: white; border-radius: 10px; padding: 20px; margin: 20px 0; box-shadow: 0 2px 8px rgba(0,0,0,.05); }",
        ".chart { min-height: 350px; }",
        "table { width: 100%; border-collapse: collapse; margin-top: 15px; }",
        "th, td { border: 1px solid #ddd; padding: 9px; text-align: left; vertical-align: top; }",
        "th { background: #eef2f6; }",
        "tr:nth-child(even) { background: #fafafa; }",
        "@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } body { padding: 12px; } table { font-size: 13px; } }",
        "</style>",
        "</head>",
        "<body>",
        '<div class="container">',
        "<h1>Панель задач Weeek</h1>",
        f'<div class="updated">Данные обновлены: {updated_at}, Красноярск</div>',
        '<div class="cards">',
        f'<div class="card"><b>Всего задач</b><span>{len(rows)}</span></div>',
        f'<div class="card"><b>Проектов</b><span>{len(project_counts)}</span></div>',
        f'<div class="card"><b>Выполнено</b><span>{status_counts.get("Выполнено", 0)}</span></div>',
        f'<div class="card"><b>Просрочено</b><span>{status_counts.get("Просрочено", 0)}</span></div>',
        f'<div class="card"><b>Не начато</b><span>{status_counts.get("Не начато", 0)}</span></div>',
        "</div>",
        '<div class="grid">',
        '<div class="panel"><h2>Задачи по статусам</h2><div class="chart"><canvas id="statusChart"></canvas></div></div>',
        '<div class="panel"><h2>Задачи по проектам</h2><div class="chart"><canvas id="projectChart"></canvas></div></div>',
        "</div>",
        '<div class="panel"><h2>Сводка по статусам</h2>',
        "<table><tr><th>Статус</th><th>Количество</th><th>Процент</th></tr>",
        "".join(status_table),
        "</table></div>",
        '<div class="panel"><h2>Сводка по проектам</h2>',
        "<table><tr><th>Проект</th><th>Количество задач</th></tr>",
        "".join(project_table),
        "</table></div>",
        '<div class="panel"><h2>Все задачи</h2>',
        "<table><tr><th>ID</th><th>Проект</th><th>Задача</th><th>Статус</th><th>Срок</th></tr>",
        "".join(task_table),
        "</table></div>",
        "<script>",
        "new Chart(document.getElementById('statusChart'), {",
        "type: 'bar',",
        "data: {",
        f"labels: {json.dumps(status_labels, ensure_ascii=False)},",
        f"datasets: [{{ label: 'Количество задач', data: {json.dumps(status_values)}, backgroundColor: ['#38a169', '#e53e3e', '#dd6b20', '#718096', '#805ad5'] }}]",
        "},",
        "options: { responsive: true, maintainAspectRatio: false, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }",
        "});",
        "new Chart(document.getElementById('projectChart'), {",
        "type: 'bar',",
        "data: {",
        f"labels: {json.dumps(project_labels, ensure_ascii=False)},",
        f"datasets: [{{ label: 'Количество задач', data: {json.dumps(project_values)}, backgroundColor: '#4299e1' }}]",
        "},",
        "options: { indexAxis: 'y', responsive: true, maintainAspectRatio: false, scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } }",
        "});",
        "</script>",
        "</div>",
        "</body>",
        "</html>",
    ]

    with open("index.html", "w", encoding="utf-8") as file:
        file.write("\n".join(html_lines))


def main():
    projects = get_projects()
    project_names = {
        project.get("id"): (
            project.get("title")
            or project.get("name")
            or f"Проект {project.get('id')}"
        )
        for project in projects
    }

    all_tasks = []

    for project in projects:
        project_id = project.get("id")
        project_tasks = get_tasks_for_project(project_id)

        for task in project_tasks:
            task["projectId"] = project_id

        all_tasks.extend(project_tasks)

    rows = prepare_rows(all_tasks, project_names)

    save_csv(rows)
    save_json(rows)
    save_html(rows)

    print("Готово.")
    print(f"Проектов: {len(projects)}")
    print(f"Уникальных задач: {len(rows)}")


if __name__ == "__main__":
    main()
