from datetime import datetime, timedelta
from typing import Any


def validate_dependencies(tasks: list[dict[str, Any]]) -> list[str]:
    """Validate task names, dependencies, missing references, and cycles."""
    errors = []
    names = [task.get("task", "").strip() for task in tasks]
    name_set = set(names)

    if "" in names:
        errors.append("Every task must have a non-empty task name.")

    if len(names) != len(name_set):
        errors.append("Task names must be unique.")

    graph = {}

    for task in tasks:
        name = task.get("task", "").strip()
        dependencies = task.get("depends_on", []) or []

        if not isinstance(dependencies, list):
            errors.append(f"Dependencies for '{name}' must be a list.")
            continue

        graph[name] = dependencies

        for dependency in dependencies:
            if not isinstance(dependency, str):
                errors.append(
                    f"Dependencies for '{name}' must contain task names."
                )
                continue

            if dependency not in name_set:
                errors.append(
                    f"Task '{name}' depends on missing task '{dependency}'."
                )

            if dependency == name:
                errors.append(f"Task '{name}' cannot depend on itself.")

    visited = set()
    active = set()

    def visit(name):
        if name in active:
            return True

        if name in visited or name not in graph:
            return False

        active.add(name)

        for dependency in graph[name]:
            if dependency in graph and visit(dependency):
                return True

        active.remove(name)
        visited.add(name)
        return False

    for name in graph:
        if visit(name):
            errors.append(
                "Circular dependencies detected. Review the task dependency chain."
            )
            break

    return list(dict.fromkeys(errors))


def schedule_tasks_by_dependencies(
    tasks: list[dict[str, Any]],
    candidate_windows: list[dict[str, Any]],
    events: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Schedule tasks into available windows.

    Features:
    - Dependencies are scheduled before dependent tasks.
    - Tasks are placed in available windows without overlaps.
    - Tasks can move to later windows when an earlier window is unsuitable.
    - Deadlines are enforced using task end times.
    - Unscheduled tasks receive null suggested_start/suggested_end values.

    Windows and events must have timezone-aware ISO timestamps or datetime values.
    """
    result = [dict(task) for task in tasks]
    events = events or []

    dependency_errors = validate_dependencies(result)
    if dependency_errors:
        return result, dependency_errors

    by_name = {task["task"].strip(): task for task in result}

    def parse_time(value):
        if isinstance(value, datetime):
            return value

        if not isinstance(value, str):
            raise ValueError("Timestamp must be a string or datetime.")

        return datetime.fromisoformat(value.replace("Z", "+00:00"))

    def valid_interval(start, end):
        return (
            start.tzinfo is not None
            and start.utcoffset() is not None
            and end.tzinfo is not None
            and end.utcoffset() is not None
            and end > start
        )

    try:
        windows = []

        for window in candidate_windows:
            start = parse_time(window["start"])
            end = parse_time(window["end"])

            if not valid_interval(start, end):
                return result, [
                    "Candidate windows must have timezone-aware start/end "
                    "times, with end after start."
                ]

            windows.append((start, end))

        windows.sort(key=lambda interval: interval[0])

        busy = []

        for event in events:
            if not event.get("start") or not event.get("end"):
                continue

            start = parse_time(event["start"])
            end = parse_time(event["end"])

            if not valid_interval(start, end):
                return result, [
                    "Calendar events must have timezone-aware valid "
                    "start/end times."
                ]

            busy.append((start, end))

        busy.sort(key=lambda interval: interval[0])

    except (KeyError, TypeError, ValueError) as exc:
        return result, [f"Invalid window or event timestamp: {exc}"]

    # Stable topological ordering: dependencies first, then higher priority.
    ordered = []
    completed = set()
    remaining = set(by_name)

    while remaining:
        ready = [
            by_name[name]
            for name in remaining
            if all(
                dependency in completed
                for dependency in (by_name[name].get("depends_on", []) or [])
            )
        ]

        if not ready:
            return result, [
                "Unable to order tasks due to invalid dependencies."
            ]

        ready.sort(
            key=lambda task: (
                -float(task.get("priority_score", 0) or 0),
                task["task"].strip().casefold(),
            )
        )

        chosen = ready[0]
        name = chosen["task"].strip()
        ordered.append(chosen)
        completed.add(name)
        remaining.remove(name)

    errors = []
    scheduled_end = {}

    for task in ordered:
        name = task["task"].strip()

        # Clear stale scheduling values before recalculating the plan.
        task["suggested_start"] = None
        task["suggested_end"] = None

        raw_duration = task.get("estimated_duration_minutes")

        try:
            if isinstance(raw_duration, bool):
                raise ValueError

            duration = int(raw_duration)

            if float(raw_duration) != duration or duration <= 0:
                raise ValueError

        except (TypeError, ValueError, OverflowError):
            errors.append(f"Task '{name}' has an invalid duration.")
            continue

        duration_delta = timedelta(minutes=duration)

        dependencies = task.get("depends_on", []) or []

        if any(dependency not in scheduled_end for dependency in dependencies):
            errors.append(
                f"Task '{name}' cannot be scheduled because a prerequisite "
                "was not scheduled."
            )
            continue

        earliest_start = (
            max(scheduled_end[dependency] for dependency in dependencies)
            if dependencies
            else None
        )

        deadline = None

        try:
            if task.get("deadline"):
                deadline = parse_time(task["deadline"])

                if deadline.tzinfo is None or deadline.utcoffset() is None:
                    raise ValueError("Deadline must include a timezone.")

        except (TypeError, ValueError) as exc:
            errors.append(f"Task '{name}' has an invalid deadline: {exc}")
            continue

        placed = False

        for window_start, window_end in windows:
            start = (
                max(window_start, earliest_start)
                if earliest_start is not None
                else window_start
            )

            # Search this window, moving forward past any conflicts.
            while start + duration_delta <= window_end:
                end = start + duration_delta

                # A deadline applies to task completion, not just task start.
                if deadline is not None and end > deadline:
                    break

                conflict = next(
                    (
                        (busy_start, busy_end)
                        for busy_start, busy_end in busy
                        if start < busy_end and end > busy_start
                    ),
                    None,
                )

                if conflict is not None:
                    start = conflict[1]
                    continue

                task["suggested_start"] = start.isoformat()
                task["suggested_end"] = end.isoformat()
                scheduled_end[name] = end

                busy.append((start, end))
                busy.sort(key=lambda interval: interval[0])

                placed = True
                break

            if placed:
                break

        if not placed:
            if deadline is not None:
                errors.append(
                    f"Task '{name}' could not be scheduled within the "
                    "available windows and before its deadline."
                )
            else:
                errors.append(
                    f"Task '{name}' could not be scheduled within the "
                    "available windows."
                )

    return ordered, list(dict.fromkeys(errors))