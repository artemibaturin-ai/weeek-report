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
        tasks = data.get("tasks")
        if tasks is None:
            tasks = data.get("data", [])
        return tasks

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
    completed = task.get("completed")

    if isinstance(completed, bool):
        return completed

    status = task_status(task).lower()

    return status in {
        "done",
        "completed",
        "complete",
        "выполнено",
        "завершено",
    }


def is_overdue(task):
    due_date =
