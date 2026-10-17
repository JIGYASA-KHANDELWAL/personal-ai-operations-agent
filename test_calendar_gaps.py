
from datetime import datetime, timedelta
from app.agents.planner import validate_task_timings

candidate_windows = [
    {
        "start": "2026-10-19T09:00:00+05:30",
        "end": "2026-10-19T11:00:00+05:30",
        "duration_minutes": 120,
    }
]

events = [
    {
        "summary": "Team Meeting",
        "start": {"dateTime": "2026-10-19T10:00:00+05:30"},
        "end": {"dateTime": "2026-10-19T10:30:00+05:30"},
    }
]

tasks = [
    {
        "task": "Prepare workshop slides",
        "description": "Create the first draft.",
        "priority": "High",
        "estimated_duration_minutes": 60,
        "suggested_start": "2026-10-19T09:45:00+05:30",
        "suggested_end": "2026-10-19T10:45:00+05:30",
    }
]

errors = validate_task_timings(tasks, candidate_windows, events)

print("Validation errors:")
if errors:
    for error in errors:
        print("-", error)
else:
    print("None")
