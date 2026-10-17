from datetime import datetime

from app.agents.dependency_scheduler import (
    schedule_tasks_by_dependencies,
    validate_dependencies,
)


def window(start, end):
    return {
        "start": f"2026-10-19T{start}:00+05:30",
        "end": f"2026-10-19T{end}:00+05:30",
    }


def test_moves_to_later_window():
    tasks = [
        {
            "task": "Prepare report",
            "estimated_duration_minutes": 90,
            "depends_on": [],
        }
    ]

    windows = [
        window("09:00", "10:00"),
        window("11:00", "13:00"),
    ]

    scheduled, errors = schedule_tasks_by_dependencies(tasks, windows)

    assert not errors, errors
    assert scheduled[0]["suggested_start"].startswith(
        "2026-10-19T11:00"
    )
    assert scheduled[0]["suggested_end"].startswith(
        "2026-10-19T12:30"
    )


def test_dependent_task_starts_after_prerequisite():
    tasks = [
        {
            "task": "Finish design",
            "estimated_duration_minutes": 60,
            "depends_on": [],
        },
        {
            "task": "Publish design",
            "estimated_duration_minutes": 30,
            "depends_on": ["Finish design"],
        },
    ]

    scheduled, errors = schedule_tasks_by_dependencies(
        tasks, [window("09:00", "12:00")]
    )

    assert not errors, errors

    by_name = {task["task"]: task for task in scheduled}

    end_design = datetime.fromisoformat(
        by_name["Finish design"]["suggested_end"]
    )
    start_publish = datetime.fromisoformat(
        by_name["Publish design"]["suggested_start"]
    )

    assert start_publish >= end_design


def test_impossible_deadline_reports_unscheduled():
    tasks = [
        {
            "task": "Submit report",
            "estimated_duration_minutes": 120,
            "depends_on": [],
            "deadline": "2026-10-19T10:00:00+05:30",
        }
    ]

    scheduled, errors = schedule_tasks_by_dependencies(
        tasks, [window("09:00", "12:00")]
    )

    assert errors
    assert scheduled[0]["suggested_start"] is None
    assert scheduled[0]["suggested_end"] is None


def test_circular_dependencies_rejected():
    tasks = [
        {
            "task": "Task A",
            "estimated_duration_minutes": 30,
            "depends_on": ["Task B"],
        },
        {
            "task": "Task B",
            "estimated_duration_minutes": 30,
            "depends_on": ["Task A"],
        },
    ]

    errors = validate_dependencies(tasks)
    assert any("Circular dependencies" in error for error in errors)


def test_calendar_event_is_avoided():
    tasks = [
        {
            "task": "Study",
            "estimated_duration_minutes": 60,
            "depends_on": [],
        }
    ]

    events = [
        {
            "start": "2026-10-19T09:00:00+05:30",
            "end": "2026-10-19T10:00:00+05:30",
        }
    ]

    scheduled, errors = schedule_tasks_by_dependencies(
        tasks, [window("09:00", "12:00")], events
    )

    assert not errors, errors
    assert scheduled[0]["suggested_start"].startswith(
        "2026-10-19T10:00"
    )


if __name__ == "__main__":
    test_moves_to_later_window()
    test_dependent_task_starts_after_prerequisite()
    test_impossible_deadline_reports_unscheduled()
    test_circular_dependencies_rejected()
    test_calendar_event_is_avoided()

    print("All scheduler edge-case tests passed.")