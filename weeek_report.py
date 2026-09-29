import csv
import html
import json
import os
import sys
from collections import Counter
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TOKEN = os.environ.get("WEEEK_TOKEN")

if not TOKEN:
    print("Ошибка: секрет WEEEK_TOKEN не передан")
    sys.exit(1)

BASE_URL = "https://api.weeek.net/public/v1"


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
    page = 1

    while True:
        result = api_get(
            "/tm/tasks",
            {
                "projectId": project_id,
                "page": page,
            },
        )

        tasks = result.get("tasks", [])
        all_tasks.extend(tasks)

        print(
            f"Проект {project_id}, страница {page}: "
            f"получено задач — {len(tasks)}"
        )

        if not result.get("hasMore") or not tasks:
            break

        page += 1

        if page > 100:
            print(f"Проект {project_id}: остановка после 100 страниц")
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


def make_rows(tasks, project_names):
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

    status_labels = list(status_counts.keys())
    status_values = [status_counts[label] for label in status_labels]

    project_labels = list(project_counts.keys())
    project_values = [project_counts[label] for label in project_labels]

    status_table = ""

    for status, count in status_counts.items():
        percent = round(count / len(rows) * 100, 1) if rows else 0

        status_table += f"""
        <tr>
            <td>{html.escape(status)}</td>
            <td>{count}</td>
            <td>{percent}%</td>
        </tr>
        """

    project_table = ""

    for project, count in project_counts.items():
        project_table += f"""
        <tr>
            <td>{html.escape(project)}</td>
            <td>{count}</td>
        </tr>
        """

    task_table = ""

    for row in rows:
        task_table += f"""
        <tr>
            <td>{row["id"]}</td>
            <td>{html.escape(row["project"])}</td>
            <td>{html.escape(row["title"])}</td>
            <td>{html.escape(row["status"])}</td>
            <td>{html.escape(str(row["dueDate"]))}</td>
        </tr>
        """

    html_report = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Отчет Weeek</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
body {{
    font-family: Arial, sans-serif;
    margin: 30px;
    color: #222;
}}

h1, h2 {{
    color: #333;
}}

.cards {{
    display: flex;
    flex-wrap: wrap;
    gap: 15px;
    margin: 20px 0;
}}

.card {{
    min-width: 150px;
    padding: 18px;
    border: 1px solid #ddd;
    border-radius: 10px;
    background: #f7f7f7;
}}

.card span {{
    display: block;
    margin-top: 8px;
    font-size: 25px;
    font-weight: bold;
}}

.chart {{
    max-width: 900px;
    margin: 25px 0 45px;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    margin: 15px 0 40px;
}}

th, td {{
    border: 1px solid #ddd;
    padding: 8px;
    text-align: left;
}}

th {{
    background: #f0f0f0;
}}

tr:nth-child(even) {{
    background: #fafafa;
}}
</style>
</head>

<body>

<h1>Отчет по задачам Weeek</h1>
<p>В отчет включены задачи всех проектов.</p>

<div class="cards">
    <div class="card">
        <b>Всего задач</b>
        <span>{len(rows)}</span>
    </div>

    <div class="card">
        <b>Проектов</b>
        <span>{len(project_counts)}</span>
    </div>

    <div class="card">
        <b>Выполнено</b>
        <span>{status_counts.get("Выполнено", 0)}</span>
    </div>

    <div class="card">
        <b>Просрочено</b>
        <span>{status_counts.get("Просрочено", 0)}</span>
    </div>

    <div class="card">
        <b>Не начато</b>
        <span>{status_counts.get("Не начато", 0)}</span>
    </div>
</div>

<h2>Задачи по статусам</h2>
<div class="chart">
    <canvas id="statusChart"></canvas>
</div>

<h2>Задачи по проектам</h2>
<div class="chart">
    <canvas id="projectChart"></canvas>
</div>

<h2>Сводка по статусам</h2>
<table>
<tr>
    <th>Статус</th>
    <th>Количество</th>
    <th>Процент</th>
</tr>
{status_table}
</table>

<h2>Сводка по проектам</h2>
<table>
<tr>
    <th>Проект</th>
    <th>Количество задач</th>
</tr>
{project_table}
</table>

<h2>Все задачи</h2>
<table>
<tr>
    <th>ID</th>
    <th>Проект</th>
    <th>Задача</th>
    <th>Статус</th>
    <th>Срок</th>
</tr>
{task_table}
</table>

<script>
new Chart(document.getElementById("statusChart"), {{
    type: "bar",
    data: {{
        labels: {json.dumps(status_labels, ensure_ascii=False)},
        datasets: [{{
            label: "Количество задач",
            data: {json.dumps(status_values)},
            backgroundColor: [
                "#38a169",
                "#e53e3e",
                "#dd6b20",
                "#718096",
                "#805ad5"
            ]
        }}]
    }},
    options: {{
        responsive: true,
        scales: {{
            y: {{
                beginAtZero: true,
                ticks: {{ precision: 0 }}
            }}
        }}
    }}
}});

new Chart(document.getElementById("projectChart"), {{
    type: "bar",
    data: {{
        labels: {json.dumps(project_labels, ensure_ascii=False)},
        datasets: [{{
            label: "Количество задач",
            data: {json.dumps(project_values)},
            backgroundColor: "#4299e1"
        }}]
    }},
    options: {{
        indexAxis: "y",
        responsive: true,
        scales: {{
            x: {{
                beginAtZero: true,
                ticks: {{ precision: 0 }}
            }}
        }}
    }}
}});
</script>

</body>
</html>
"""

    with open("weeek_report.html", "w", encoding="utf-8") as file:
        file.write(html_report)


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

    rows = make_rows(all_tasks, project_names)

    save_csv(rows)
    save_json(rows)
    save_html(rows)

    print()
    print("Готово.")
    print(f"Проектов обработано: {len(projects)}")
    print(f"Задач обработано: {len(rows)}")
    print("Созданы файлы:")
    print("- weeek_report.html")
    print("- weeek_tasks.csv")
    print("- weeek_tasks.json")


if __name__ == "__main__":
    main()
