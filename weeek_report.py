import csv
import json
import os
from datetime import datetime
from pathlib import Path

import requests


BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
PUBLIC_DIR.mkdir(exist_ok=True)

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
    return (
        task.get("title")
        or task.get("name")
        or task.get("text")
        or "Без названия"
    )


def task_status(task):
    status = task.get("status")

    if isinstance(status, dict):
        return (
            status.get("name")
            or status.get("title")
            or status.get("id")
            or "Не указан"
        )

    return str(status or "Не указан")


def task_project(task):
    project = task.get("project")

    if isinstance(project, dict):
        return (
            project.get("name")
            or project.get("title")
            or project.get("id")
            or "Без проекта"
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
        date_text = str(due_date)[:10]
        due = datetime.strptime(date_text, "%Y-%m-%d").date()
        return due < datetime.now().date()
    except ValueError:
        return False


def make_csv(tasks):
    csv_path = PUBLIC_DIR / "weeek_tasks.csv"

    fieldnames = [
        "title",
        "status",
        "project",
        "due_date",
        "completed",
        "overdue",
    ]

    with csv_path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
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
    json_path = PUBLIC_DIR / "weeek_tasks.json"

    with json_path.open("w", encoding="utf-8") as file:
        json.dump(tasks, file, ensure_ascii=False, indent=2)


def make_html(tasks):
    updated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

    total = len(tasks)
    completed = sum(is_completed(task) for task in tasks)
    overdue = sum(is_overdue(task) for task in tasks)
    not_started = total - completed

    projects = {
        task_project(task)
        for task in tasks
    }

    rows = []

    for task in tasks:
        title = task_title(task)
        status = task_status(task)
        project = task_project(task)
        due_date = task_due_date(task)

        rows.append(
            f"""
            <tr>
              <td>{title}</td>
              <td>{status}</td>
              <td>{project}</td>
              <td>{due_date}</td>
            </tr>
            """
        )

    html = f"""<!doctype html>
<html lang="ru">
