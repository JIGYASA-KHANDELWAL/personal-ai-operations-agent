"""Decision support utilities for the Personal AI Operations Agent.

These functions analyze saved plans and propose schedule changes locally.
They do not modify Google Calendar or send external messages.
"""
from datetime import datetime, timedelta


def _parse(value, now):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=now.tzinfo)
        return parsed.astimezone(now.tzinfo)
    except (TypeError, ValueError, OverflowError):
        return None


def analyze_operations(tasks, tracking, now=None):
    """Return actionable risks and task-level explanations for a plan."""
    now = now or datetime.now().astimezone()
    task_by_name = {t.get("task", "").strip(): t for t in tasks}
    status_by_name = {}
    for i, task in enumerate(tasks):
        status_by_name[task.get("task", "").strip()] = tracking.get(i, {}).get("status", "Pending")

    findings = []
    for i, task in enumerate(tasks):
        name = task.get("task", f"Task {i+1}")
        status = tracking.get(i, {}).get("status", "Pending")
        if status == "Completed":
            continue
        reasons, severity = [], "Info"
        deadline = _parse(task.get("deadline"), now)
        if status == "Blocked":
            reasons.append("Task is marked Blocked")
            severity = "High"
        if deadline and deadline < now:
            reasons.append("Deadline has passed")
            severity = "High"
        elif deadline and deadline <= now + timedelta(days=1):
            reasons.append("Deadline is within 24 hours")
            severity = "High" if severity != "High" else severity
        elif deadline and deadline <= now + timedelta(days=3):
            reasons.append("Deadline is within 3 days")
            severity = "Medium" if severity == "Info" else severity

        start = _parse(task.get("suggested_start"), now)
        end = _parse(task.get("suggested_end"), now)
        if not start or not end:
            reasons.append("No valid scheduled time")
            severity = "Medium" if severity == "Info" else severity

        dependencies = task.get("depends_on", []) or []
        incomplete_deps = [dep for dep in dependencies if status_by_name.get(dep) != "Completed"]
        if incomplete_deps:
            reasons.append("Waiting on: " + ", ".join(incomplete_deps))
            severity = "High" if any(status_by_name.get(d) == "Blocked" for d in incomplete_deps) else ("Medium" if severity == "Info" else severity)

        if reasons:
            findings.append({
                "task": name, "status": status, "severity": severity,
                "reasons": reasons, "deadline": task.get("deadline"),
                "priority_score": task.get("priority_score", 0),
            })

    order = {"High": 0, "Medium": 1, "Info": 2}
    findings.sort(key=lambda x: (order[x["severity"]], -float(x["priority_score"] or 0)))
    return findings


def summarize_portfolio(plans, tracking_getter):
    """Aggregate progress across saved plans."""
    total_tasks = completed = blocked = in_progress = 0
    plan_rows = []
    for plan in plans:
        import json
        try:
            tasks = json.loads(plan["tasks_json"])
        except (ValueError, TypeError):
            tasks = []
        tracking = tracking_getter(plan["id"])
        counts = {"Completed": 0, "Blocked": 0, "In Progress": 0, "Pending": 0}
        for i in range(len(tasks)):
            status = tracking.get(i, {}).get("status", "Pending")
            counts[status if status in counts else "Pending"] += 1
        total = len(tasks)
        total_tasks += total
        completed += counts["Completed"]
        blocked += counts["Blocked"]
        in_progress += counts["In Progress"]
        plan_rows.append({
            "id": plan["id"], "goal": plan["goal"], "created_at": plan["created_at"],
            "total": total, "completed": counts["Completed"], "blocked": counts["Blocked"],
            "in_progress": counts["In Progress"],
            "percentage": round(100 * counts["Completed"] / total, 1) if total else 0,
        })
    return {
        "plans": len(plans), "total_tasks": total_tasks, "completed": completed,
        "blocked": blocked, "in_progress": in_progress,
        "pending": total_tasks - completed - blocked - in_progress,
        "percentage": round(100 * completed / total_tasks, 1) if total_tasks else 0,
        "plan_rows": plan_rows,
    }


def propose_reschedule(tasks, tracking, calendar_events, now=None, days=7):
    """Propose new times for unfinished tasks; completed tasks remain untouched."""
    from tools.calendar_tool import calculate_free_gaps
    from agents.dependency_scheduler import schedule_tasks_by_dependencies

    now = now or datetime.now().astimezone()
    completed_names = {
        task.get("task", "").strip()
        for i, task in enumerate(tasks)
        if tracking.get(i, {}).get("status", "Pending") == "Completed"
    }
    remaining = []
    original_by_name = {}
    for i, task in enumerate(tasks):
        name = task.get("task", f"Task {i+1}")
        original_by_name[name] = task
        if tracking.get(i, {}).get("status", "Pending") == "Completed":
            continue
        clone = dict(task)
        # A completed prerequisite is already satisfied; remove it from the
        # scheduling graph without altering the saved plan.
        clone["depends_on"] = [d for d in (task.get("depends_on", []) or []) if d not in completed_names]
        remaining.append(clone)

    gaps = calculate_free_gaps(
        calendar_events or [], start_date=now.date(), days=days,
        day_start_hour=9, day_end_hour=20,
    )
    flat_events = []
    for event in calendar_events or []:
        start = event.get("start", {}).get("dateTime")
        end = event.get("end", {}).get("dateTime")
        if start and end:
            flat_events.append({"start": start, "end": end})

    scheduled, errors = schedule_tasks_by_dependencies(remaining, gaps, flat_events)
    return {
        "tasks": scheduled,
        "errors": errors,
        "completed_unchanged": sorted(completed_names),
        "message": "Preview only. No saved plan or Google Calendar event has been changed.",
    }
