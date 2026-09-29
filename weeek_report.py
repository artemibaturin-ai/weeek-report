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
            content = response.read().decode("utf-8")
            return json.loads(content)

    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(f"Ошибка API: HTTP {error.code}")
        print(f"Адрес: {url}")
        print(body)
        sys.exit(1)

    except URLError as error:
        print(f"Ошибка соединения: {error.reason}")
        sys.exit(1)


def get_all_projects():
    result = api_get("/tm/projects")
    projects = result.get("projects", [])

    project_names = {}

    for project in projects:
        project_id = project.get("id")
        project_name = (
            project.get("title")
            or project.get("name")
            or f"Проект {project_id}"
        )

        project_names[project_id] = project_name

    print(f"Получено проектов: {len(project_names)}")
    return project_names


def get_all_tasks():
    all_tasks = []
    page = 1

    while True:
        result = api_get("/tm/tasks", {"page": page})
        tasks = result.get("tasks", [])

        all_tasks.extend(tasks)

        print(f"Страница {page}: получено задач — {len(tasks)}")

        if not result.get("hasMore") or not tasks:
            break

        page += 1

        if page > 100:
            print("Остановлено после 100 страниц")
            break

    print(f"Всего загружено задач: {len(all_tasks)}")
    return all_tasks


def get_task_status(task):
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
            "project": project_names.get(project_id, "Без проекта"),
            "projectId": project_id if project_id is not None else "",
            "title": task.get("title", ""),
            "status": get_task_status(task),
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
        "project",
        "projectId",
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


def make_html_report(rows):
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

    status_values = [
        status_counts[status]
        for status in status_labels
    ]

    project_labels = list(project_counts.keys())
    project_values = [
        project_counts[project]
        for project in project_labels
    ]

    status_labels_json = json.dumps(status_labels, ensure_ascii=False)
    status_values_json = json.dumps(status_values)

    project_labels_json = json.dumps(project_labels, ensure_ascii=False)
    project_values_json = json.dumps(project_values)

    status_rows = ""

    for status in status_labels:
        count = status_counts[status]
        percent = round(count / len(rows) * 100, 1) if rows else 0

        status_rows += f"""
        <tr>
            <td>{html.escape(status)}</td>
            <td>{count}</td>
            <td>{percent}%</td>
        </tr>
        """

    project_rows = ""

    for project in project_labels:
        project_rows += f"""
        <tr>
            <td>{html.escape(project)}</td>
            <td>{project_counts[project]}</td>
        </tr>
        """

    task_rows = ""

    for row in rows:
        task_rows += f"""
        <tr>
            <td>{row["id"]}</td>
            <td>{html.escape(row["project"])}</td>
            <td>{html.escape(row["title"])}</td>
            <td>{html.escape(row["status"])}</td>
            <td>{html.escape(str(row["dueDate"]))}</td>
        </tr>
        """

    report = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Отчет по задачам Weeek</title>

<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>

<style>
body {{
    font-family: Arial, sans-serif;
    margin: 30px;
    color: #222;
    background: #fff;
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

.card b {{
    font-size: 14px;
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
    vertical-align: top;
}}

th {{
    background: #f0f0f0;
}}

tr:nth-child(even) {{
    background: #fafafa;
}}

.note {{
    padding: 12px;
    border-left: 4px solid #4299e1;
    background: #ebf8ff;
}}
</style>
</head>

<body>

<h1>Отчет по задачам Weeek</h1>

<div class="note">
Отчет сформирован по всем проектам и всем загруженным страницам задач.
</div>

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

<h2>Распределение задач по статусам</h2>

<div class="chart">
    <canvas id="statusChart"></canvas>
</div>

<h2>Распределение задач по проектам</h2>

<div class="chart">
    <canvas id="projectChart"></canvas>
</div>

<h2>Сводка по статусам</h2>

<table>
    <tr>
        <th>Статус</th>
        <th>Количество</th>
        <th>Доля</th>
    </tr>
    {status_rows}
</table>

<h2>Сводка по проектам</h2>

<table>
    <tr>
        <th>Проект</th>
        <th>Количество задач</th>
    </tr>
    {project_rows}
</table>

<h2>Полный список задач</h2>

<table>
    <tr>
        <th>ID</th>
        <th>Проект</th>
        <th>Задача</th>
        <th>Статус</th>
        <th>Срок</th>
    </tr>
    {task_rows}
</table>

<script>
const statusLabels = {status_labels_json};
const statusValues = {status_values_json};

new Chart(document.getElementById("statusChart"), {{
    type: "bar",
    data: {{
        labels: statusLabels,
        datasets: [{{
            label: "Количество задач",
            data: statusValues,
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
                ticks: {{
                    precision: 0
                }}
            }}
        }}
    }}
}});

const projectLabels = {project_labels_json};
const projectValues = {project_values_json};

new Chart(document.getElementById("projectChart"), {{
    type: "bar",
    data: {{
        labels: projectLabels,
        datasets: [{{
            label: "Количество задач",
            data: projectValues,
            backgroundColor: "#4299e1"
        }}]
    }},
    options: {{
        indexAxis: "y",
        responsive: true,
        scales: {{
            x: {{
                beginAtZero: true,
                ticks: {{
                    precision: 0
                }}
            }}
        }}
    }}
}});
</script>

</body>
</html>
"""

    with open("weeek_report.html", "w", encoding="utf-8") as file:
        file.write(report)


def save_json(rows):
    with open("weeek_tasks.json", "w", encoding="utf-8") as file:
        json.dump(rows, file, ensure_ascii=False, indent=2)


def main():
    print("Получение проектов...")
    project_names = get_all_projects()

    print("Получение задач...")
    tasks = get_all_tasks()

    rows = prepare_rows(tasks, project_names)

    save_csv(rows)
    save_json(rows)
    make_html_report(rows)

    print()
    print("Готово.")
    print(f"Всего задач: {len(rows)}")
    print(f"Проектов: {len(set(row['project'] for row in rows))}")
    print()
    print("Созданы файлы:")
    print("weeek_report.html")
    print("weeek_tasks.csv")
    print("weeek_tasks.json")


if __name__ == "__main__":
    main()
