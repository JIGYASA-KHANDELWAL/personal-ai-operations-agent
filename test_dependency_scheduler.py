
from datetime import datetime, timedelta

from app.agents.dependency_scheduler import (
    schedule_tasks_by_dependencies,
    validate_dependencies,
)


zone = "+05:30"
base = datetime.fromisoformat(f"2026-10-19T09:00:00{zone}")

windows = [
    {
        "start": base.isoformat(),
        "end": (base + timedelta(hours=8)).isoformat(),
    }
]

tasks = [
    {
        "task": "Publish announcement",
        "estimated_duration_minutes": 30,
        "depends_on": ["Prepare posters"],
        "priority_score": 100,
        "deadline": None,
    },
    {
        "task": "Prepare posters",
        "estimated_duration_minutes": 60,
        "depends_on": ["Finalize venue"],
        "priority_score": 20,
        "deadline": None,
    },
    {
        "task": "Finalize venue",
        "estimated_duration_minutes": 60,
        "depends_on": [],
        "priority_score": 10,
        "deadline": None,
    },
]

scheduled, errors = schedule_tasks_by_dependencies(
    tasks=tasks,
    candidate_windows=windows,
    events=[],
)

assert not errors, errors
assert [task["task"] for task in scheduled] == [
    "Finalize venue",
    "Prepare posters",
    "Publish announcement",
]

by_name = {task["task"]: task for task in scheduled}

assert (
    datetime.fromisoformat(by_name["Prepare posters"]["suggested_start"])
    >= datetime.fromisoformat(by_name["Finalize venue"]["suggested_end"])
)

assert (
    datetime.fromisoformat(by_name["Publish announcement"]["suggested_start"])
    >= datetime.fromisoformat(by_name["Prepare posters"]["suggested_end"])
)

circular_tasks = [
    {"task": "A", "depends_on": ["B"]},
    {"task": "B", "depends_on": ["A"]},
]

assert any(
    "Circular" in error
    for error in validate_dependencies(circular_tasks)
)

print("All dependency scheduler tests passed.")
