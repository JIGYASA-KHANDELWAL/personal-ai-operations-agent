
import os
import json
import sys
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from google import genai

# Make the app folder importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import initialize_database, save_plan
from tools.calendar_tool import (
    get_upcoming_events,
    calculate_free_gaps,
)
from app.agents.dependency_scheduler import (
    schedule_tasks_by_dependencies,
    validate_dependencies,
)

load_dotenv()

# Allow importing this module when no Gemini API key is configured.
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key) if api_key else None

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def validate_task_timings(tasks, candidate_windows, events):
    """
    Validate proposed task times against candidate windows,
    calendar commitments, and other proposed tasks.
    """
    errors = []
    parsed_tasks = []

    def parse_time(value):
        if not value:
            return None

        try:
            result = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
            if result.tzinfo is None:
                return None
            return result
        except (ValueError, AttributeError, TypeError):
            return None

    # Parse candidate work windows.
    windows = []

    for window in candidate_windows:
        start = parse_time(window.get("start"))
        end = parse_time(window.get("end"))

        if start and end and end > start:
            windows.append((start, end))

    # Parse timed calendar commitments.
    commitments = []

    for event in events:
        event_start = event.get("start", {}).get("dateTime")
        event_end = event.get("end", {}).get("dateTime")

        start = parse_time(event_start)
        end = parse_time(event_end)

        if start and end and end > start:
            commitments.append((start, end))

    # Validate each task.
    for index, task in enumerate(tasks, start=1):
        start = parse_time(task.get("suggested_start"))
        end = parse_time(task.get("suggested_end"))
        duration = task.get("estimated_duration_minutes")

        if (
            not isinstance(duration, int)
            or isinstance(duration, bool)
            or duration <= 0
        ):
            errors.append(
                f"Task {index}: duration must be a positive integer."
            )
            continue

        # Both times may be null if the task cannot be scheduled.
        if not start or not end:
            if (
                task.get("suggested_start") is None
                and task.get("suggested_end") is None
            ):
                continue

            errors.append(
                f"Task {index}: start/end must be valid "
                "timezone-aware timestamps."
            )
            continue

        if end <= start:
            errors.append(
                f"Task {index}: end must be after start."
            )
            continue

        actual_minutes = int(
            (end - start).total_seconds() // 60
        )

        if actual_minutes != duration:
            errors.append(
                f"Task {index}: scheduled duration does not match "
                "estimated_duration_minutes."
            )

        # Normalize timestamps before comparing different time zones.
        fits_window = any(
            start.astimezone(window_start.tzinfo) >= window_start
            and end.astimezone(window_end.tzinfo) <= window_end
            for window_start, window_end in windows
        )

        if not fits_window:
            errors.append(
                f"Task {index}: timing is outside the candidate windows."
            )

        for commitment_start, commitment_end in commitments:
            if (
                start < commitment_end
                and end > commitment_start
            ):
                errors.append(
                    f"Task {index}: overlaps a calendar commitment."
                )
                break

        parsed_tasks.append((index, start, end))

    # Check tasks against one another.
    for i, (index_a, start_a, end_a) in enumerate(parsed_tasks):
        for index_b, start_b, end_b in parsed_tasks[i + 1:]:
            if start_a < end_b and end_a > start_b:
                errors.append(
                    f"Tasks {index_a} and {index_b} overlap."
                )

    return errors


def calculate_priority_scores(tasks, now=None):
    """
    Calculate reproducible priority scores from 0 to 100.

    Weights:
        Importance:   40%
        Deadline:     35%
        Dependencies: 25%
    """
    from datetime import timezone

    if now is None:
        now = datetime.now().astimezone()
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    # Count how many tasks depend on each task.
    dependents = {}

    task_names = {
        task.get("task", "").strip().casefold()
        for task in tasks
        if task.get("task")
    }

    for task in tasks:
        dependencies = task.get("depends_on", [])

        if not isinstance(dependencies, list):
            continue

        for dependency in dependencies:
            if isinstance(dependency, str):
                key = dependency.strip().casefold()

                if key in task_names:
                    dependents[key] = dependents.get(key, 0) + 1

    max_dependents = max(dependents.values(), default=0)

    for task in tasks:
        # Importance: 1–5, normalized to 0–1.
        importance = task.get("importance", 3)

        if (
            not isinstance(importance, int)
            or isinstance(importance, bool)
            or not 1 <= importance <= 5
        ):
            importance = 3

        importance_score = importance / 5

        # Deadline urgency.
        deadline_value = task.get("deadline")
        urgency_score = 0.5  # Neutral when no deadline is known.

        if deadline_value:
            try:
                deadline = datetime.fromisoformat(
                    deadline_value.replace("Z", "+00:00")
                )

                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=now.tzinfo)

                deadline = deadline.astimezone(now.tzinfo)

                hours_remaining = (
                    deadline - now
                ).total_seconds() / 3600

                if hours_remaining <= 24:
                    urgency_score = 1.0
                elif hours_remaining <= 72:
                    urgency_score = 0.8
                elif hours_remaining <= 168:
                    urgency_score = 0.6
                elif hours_remaining <= 336:
                    urgency_score = 0.4
                else:
                    urgency_score = 0.2

            except (ValueError, TypeError, AttributeError):
                urgency_score = 0.5

        # Give credit to tasks that unblock other tasks.
        task_key = task.get("task", "").strip().casefold()
        dependent_count = dependents.get(task_key, 0)

        if max_dependents:
            dependency_score = dependent_count / max_dependents
        else:
            dependency_score = 0.0

        score = round(
            100 * (
                0.40 * importance_score
                + 0.35 * urgency_score
                + 0.25 * dependency_score
            ),
            2,
        )

        task["priority_score"] = score

        if score >= 75:
            task["computed_priority"] = "High"
        elif score >= 50:
            task["computed_priority"] = "Medium"
        else:
            task["computed_priority"] = "Low"

    return tasks


def create_plan(goal):
    """Generate, schedule, validate, and score an action plan."""

    if client is None:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Add it to your .env file "
            "to use AI planning."
        )

    # Fetch upcoming Google Calendar events.
    events = get_upcoming_events(max_results=100)

    free_gaps = calculate_free_gaps(
        events,
        start_date=datetime.now().date(),
        days=7,
        day_start_hour=9,
        day_end_hour=20,
    )

    # Format candidate work windows.
    formatted_gaps = []

    for gap in free_gaps:
        formatted_gaps.append(
            f"- Start: {gap['start']}, "
            f"End: {gap['end']}, "
            f"Duration: {gap['duration_minutes']} minutes"
        )

    gaps_context = (
        "\n".join(formatted_gaps)
        if formatted_gaps
        else "No candidate work windows were calculated."
    )

    # Format calendar events.
    formatted_events = []

    for event in events:
        start = event.get("start", {})
        end = event.get("end", {})

        start_value = start.get("dateTime", start.get("date"))
        end_value = end.get("dateTime", end.get("date"))

        duration_text = "Duration unknown"

        if start_value and end_value:
            try:
                start_dt = datetime.fromisoformat(
                    start_value.replace("Z", "+00:00")
                )
                end_dt = datetime.fromisoformat(
                    end_value.replace("Z", "+00:00")
                )

                total_minutes = int(
                    (end_dt - start_dt).total_seconds() // 60
                )

                if total_minutes >= 0:
                    hours, minutes = divmod(total_minutes, 60)
                    duration_text = f"{hours}h {minutes}m"

            except (ValueError, TypeError):
                duration_text = "Duration unavailable"

        formatted_events.append(
            f"- {event.get('summary', '(No title)')}: "
            f"Start: {start_value or 'Unknown'}, "
            f"End: {end_value or 'Unknown'}, "
            f"Duration: {duration_text}"
        )

    calendar_context = (
        "\n".join(formatted_events)
        if formatted_events
        else "No upcoming calendar events were found."
    )

    # Ask Gemini to create a plan.
    prompt = f"""
Create a practical action plan for this goal:
{goal}

UPCOMING GOOGLE CALENDAR EVENTS:
{calendar_context}

CANDIDATE WORK WINDOWS:
{gaps_context}

CALENDAR-AWARE SCHEDULING RULES:
- Treat calendar event start and end times as occupied periods.
- Never overlap a calendar commitment.
- Use only the candidate work windows supplied above.
- Candidate work windows cover the next seven days, from 09:00 to 20:00.
- Match task duration to the available window.
- Do not assign two tasks overlapping time periods.
- Allow reasonable transition and preparation time.
- Consider priorities, dependencies, deadlines, and task effort.
- Treat candidate windows as possible opportunities, not guaranteed availability.
- Do not invent availability or deadlines.
- Do not claim that tasks have been added to Google Calendar.

TASK RULES:
- Include 5 to 8 tasks.
- estimated_duration_minutes must be a positive integer.
- suggested_start and suggested_end must be timezone-aware ISO 8601 timestamps,
  or both null when no suitable window is available.
- Scheduled duration must match estimated_duration_minutes.
- importance must be an integer from 1 to 5.
- priority must be High, Medium, or Low.
- Include depends_on as a list of exact prerequisite task names.
- Include a deadline only when the user provides one or it is explicitly
  established in available context; otherwise use null.
- Explain each task's priority in priority_reason.
- Do not generate priority_score or computed_priority; the application calculates them.
- Do not send emails or perform external actions.

Return only a valid JSON object with this structure:
{{
  "goal": "the user's goal",
  "tasks": [
    {{
      "task": "task name",
      "description": "what needs to be done",
      "priority": "High",
      "importance": 3,
      "deadline": null,
      "estimated_duration_minutes": 60,
      "suggested_start": null,
      "suggested_end": null,
      "depends_on": [],
      "priority_reason": "Reason for this priority."
    }}
  ]
}}
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    try:
        plan = json.loads(response.text)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(
            "Gemini did not return valid JSON for the plan."
        ) from exc

    if (
        not isinstance(plan, dict)
        or not isinstance(plan.get("tasks"), list)
    ):
        raise ValueError(
            "Gemini returned an invalid plan structure."
        )

    tasks = plan["tasks"]

    # Validate dependency names and circular dependencies.
    dependency_errors = validate_dependencies(tasks)

    if dependency_errors:
        plan["validation_errors"] = dependency_errors
        plan["tasks"] = calculate_priority_scores(tasks)
        return plan

    # Flatten timed calendar events for the dependency scheduler.
    scheduler_events = []

    for event in events:
        start_value = event.get("start", {}).get("dateTime")
        end_value = event.get("end", {}).get("dateTime")

        if start_value and end_value:
            scheduler_events.append({
                "start": start_value,
                "end": end_value,
            })

    # Use the existing dependency-aware scheduler.
    scheduled_tasks, scheduling_errors = (
        schedule_tasks_by_dependencies(
            tasks=tasks,
            candidate_windows=free_gaps,
            events=scheduler_events,
        )
    )

    # Validate the actual scheduled result.
    timing_errors = validate_task_timings(
        scheduled_tasks,
        free_gaps,
        events,
    )

    plan["validation_errors"] = list(dict.fromkeys(
        scheduling_errors + timing_errors
    ))

    plan["tasks"] = calculate_priority_scores(scheduled_tasks)

    return plan


if __name__ == "__main__":
    initialize_database()

    goal = input("What would you like to accomplish? ").strip()

    if not goal:
        print("Please enter a goal.")
        raise SystemExit(1)

    plan = create_plan(goal)
    plan_id = save_plan(goal, plan["tasks"])

    print("\n--- YOUR ACTION PLAN ---\n")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    print(f"\nPlan saved successfully! Plan ID: {plan_id}")
