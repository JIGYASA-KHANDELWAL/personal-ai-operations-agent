
from datetime import datetime, timedelta
from dateutil.parser import parse


def _parse_datetime(value):
    if not value:
        return None
    try:
        result = parse(str(value))
        if result.tzinfo is None:
            result = result.astimezone()
        return result
    except (ValueError, TypeError, OverflowError):
        return None


def build_daily_briefing(tasks, tracking, events, now=None):
    now = now or datetime.now().astimezone()
    actions = []
    blockers = []
    completed = 0

    for index, task in enumerate(tasks):
        saved = tracking.get(index, {})
        status = saved.get("status", "Pending")
        name = task.get("task", f"Task {index + 1}")

        if status == "Completed":
            completed += 1
            continue

        if status == "Blocked":
            blockers.append({
                "task": name,
                "notes": saved.get("notes", "")
            })
            continue

        deadline = _parse_datetime(task.get("deadline"))
        score = float(task.get("priority_score", 0) or 0)
        duration = task.get("estimated_duration_minutes") or 30

        try:
            duration = max(1, int(duration))
        except (ValueError, TypeError):
            duration = 30

        reasons = []

        if status == "In Progress":
            score += 15
            reasons.append("Already in progress")

        if deadline:
            if deadline < now:
                score += 100
                reasons.append("Deadline has passed")
            elif deadline <= now + timedelta(hours=24):
                score += 50
                reasons.append("Due within 24 hours")
            elif deadline <= now + timedelta(days=3):
                score += 20
                reasons.append("Due within 3 days")

        if not reasons:
            reasons.append("Ranked by task priority")

        actions.append({
            "task": name,
            "status": status,
            "score": round(score, 2),
            "duration": duration,
            "deadline": deadline,
            "reason": " · ".join(reasons),
            "suggested_start": task.get("suggested_start"),
            "suggested_end": task.get("suggested_end"),
        })

    actions.sort(key=lambda item: item["score"], reverse=True)

    upcoming = []
    for event in events or []:
        start_data = event.get("start", {})
        start_value = start_data.get("dateTime") or start_data.get("date")
        start = _parse_datetime(start_value)

        if start and start >= now:
            upcoming.append({
                "title": event.get("summary", "(No title)"),
                "start": start,
            })

    upcoming.sort(key=lambda item: item["start"])

    return {
        "actions": actions,
        "blockers": blockers,
        "completed": completed,
        "total": len(tasks),
        "upcoming_events": upcoming,
    }
