import os
import json
import sys
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from datetime import datetime
from app.agents.dependency_scheduler import (schedule_tasks_by_dependencies,validate_dependencies,)
# Make the app folder importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from database import initialize_database, save_plan
from tools.calendar_tool import (get_upcoming_events,calculate_free_gaps,)

load_dotenv()

client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")


def validate_task_timings(tasks, candidate_windows, events):
    """
    Validate proposed task times against candidate windows,
    calendar commitments, and other proposed tasks.
    """
    from datetime import datetime

    errors = []
    parsed_tasks = []

    def parse_time(value):
        if not value:
            return None

        try:
            result = datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )

            # Require timezone-aware timestamps.
            if result.tzinfo is None:
                return None

            return result
        except (ValueError, AttributeError):
            return None

    # Parse candidate windows.
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

    for index, task in enumerate(tasks, start=1):
        start = parse_time(task.get("suggested_start"))
        end = parse_time(task.get("suggested_end"))
        duration = task.get("estimated_duration_minutes")

        if not isinstance(duration, int) or isinstance(duration, bool) or duration <= 0:
            errors.append(
                f"Task {index}: duration must be a positive integer."
            )
            continue

        if not start or not end:
            # Null times are allowed when no suitable window exists.
            if (
                task.get("suggested_start") is None
                and task.get("suggested_end") is None
            ):
                continue

            errors.append(
                f"Task {index}: start/end must be valid timezone-aware timestamps."
            )
            continue

        if end <= start:
            errors.append(
                f"Task {index}: end must be after start."
            )
            continue

        actual_minutes = int((end - start).total_seconds() // 60)

        if actual_minutes != duration:
            errors.append(
                f"Task {index}: scheduled duration does not match "
                "estimated_duration_minutes."
            )

        fits_window = any(
            start >= window_start
            and end <= window_end
            and start.tzinfo == window_start.tzinfo
            for window_start, window_end in windows
        )

        if not fits_window:
            errors.append(
                f"Task {index}: timing is outside the candidate windows."
            )

        for commitment_start, commitment_end in commitments:
            if start < commitment_end and end > commitment_start:
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
    Calculate reproducible task priority scores from 0 to 100.

    Weights:
      Importance:   40%
      Deadline:     35%
      Dependencies: 25%
    """
    from datetime import datetime, timezone

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
        for dependency in task.get("depends_on", []):
            if isinstance(dependency, str):
                key = dependency.strip().casefold()
                if key in task_names:
                    dependents[key] = dependents.get(key, 0) + 1

    max_dependents = max(dependents.values(), default=0)
    results = []

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

        # Urgency: deadline proximity, normalized to 0–1.
        deadline_value = task.get("deadline")
        urgency_score = 0.5  # Neutral when no deadline is known.

        if deadline_value:
            try:
                deadline = datetime.fromisoformat(
                    deadline_value.replace("Z", "+00:00")
                )

                # Treat timezone-naive deadlines as local time.
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=now.tzinfo)

                deadline = deadline.astimezone(now.tzinfo)
                hours_remaining = (
                    deadline - now
                ).total_seconds() / 3600

                if hours_remaining <= 0:
                    urgency_score = 1.0
                elif hours_remaining <= 24:
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
                # Invalid or ambiguous deadlines do not create urgency.
                urgency_score = 0.5

        # Dependency score: tasks that unblock other tasks get credit.
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

        results.append(task)

    return results

def create_plan(goal):
    # Fetch upcoming Google Calendar events
    events = get_upcoming_events(max_results=100)
    free_gaps = calculate_free_gaps(
        events,
        start_date=datetime.now().date(),
        days=7,
        day_start_hour=9,
        day_end_hour=20,
    )
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
        else "No candidate work windows were calculated."    )

    if events:
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

                    duration = end_dt - start_dt
                    total_minutes = int(duration.total_seconds() // 60)

                    if total_minutes >= 0:
                        hours, minutes = divmod(total_minutes, 60)
                        duration_text = (
                            f"{hours}h {minutes}m"
                        )
                except ValueError:
                    duration_text = "Duration unavailable"

            formatted_events.append(
                f"- {event.get('summary', '(No title)')}: "
                f"Start: {start_value or 'Unknown'}, "
                f"End: {end_value or 'Unknown'}, "
                f"Duration: {duration_text}"
            )

        calendar_context = "\n".join(formatted_events)

    else:
        calendar_context = "No upcoming calendar events were found."


    prompt = f"""
Create a practical action plan for this goal:
{goal}

UPCOMING GOOGLE CALENDAR EVENTS:
{calendar_context}


GAPS BETWEEN CONSECUTIVE CALENDAR EVENTS:
{gaps_context}


CALENDAR-AWARE TASK SCHEDULING RULES:
- Treat each calendar event's start and end times as occupied periods.
- Use the full event duration when identifying scheduling conflicts.
- Never recommend task timings that overlap a known calendar commitment.
- Use the provided candidate work windows when recommending task timings.
- Candidate work windows cover the next seven days, from 09:00 to 20:00.
- Match each task's estimated duration to the duration of its candidate window.
- Do not suggest a task that is longer than its proposed window.
- Allow reasonable transition and preparation time before and after meetings.
- Consider task priorities, dependencies, deadlines, and the order of work.
- Clearly label estimated task durations and suggested timings.
- Treat candidate windows as possible opportunities, not guaranteed availability.
- Do not assume that every gap is suitable for focused work.
- If a deadline or availability is unclear, state the uncertainty.
- If no suitable window exists, recommend another day or explain the limitation.
- Never invent confirmed availability or deadlines.
- Do not claim that tasks have been added to Google Calendar.


TASK TIMING AND OUTPUT RULES:
- Every task must include estimated_duration_minutes as a positive integer.
- Every task must include suggested_start and suggested_end in ISO 8601 format with a timezone offset.
- Use only candidate work windows supplied in the prompt for suggested task timings.
- Ensure suggested_end is after suggested_start.
- Ensure the time between suggested_start and suggested_end matches estimated_duration_minutes.
- Ensure every suggested task fits completely within a suitable candidate window.
- Do not assign two tasks overlapping time periods.
- Leave reasonable buffers between tasks and around calendar commitments.
- Use dates within the provided seven-day planning horizon.
- If no suitable candidate window is available, set suggested_start and suggested_end to null and explain why in the task description.
- Do not copy example dates from the JSON schema.

PRIORITIZATION RULES:
- Assign importance an integer from 1 to 5, where 5 is most important.
- Include a deadline only when the user provides one or it is explicitly
  established in the available context. Otherwise use null.
- Never invent deadlines.
- Include depends_on as a list of prerequisite task names.
- Schedule prerequisite tasks before dependent tasks.
- Explain the priority in priority_reason.
- Consider urgency, importance, dependencies, and estimated effort.
- Use High, Medium, or Low for priority.
- importance must be an integer from 1 to 5.
- depends_on must be a list of exact task names, or an empty list.
- priority_score is calculated by the application; do not generate it.
- computed_priority is calculated by the application; do not generate it.
- Never invent deadlines.

Return a JSON object with this exact structure:
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
    "suggested_start": "2026-10-19T09:00:00+05:30",
    "suggested_end": "2026-10-19T10:00:00+05:30",
    "depends_on": [],
    "priority_reason": "Reason for this priority."
   }}
  ]
}}



Include 5 to 8 tasks. Priority must be High, Medium, or Low.
Return only valid JSON. Do not use Markdown code fences.
Do not send emails, schedule events, or perform external actions.
"""

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )


    
    plan = json.loads(response.text)

    # Validate the initial plan.
    validation_errors = validate_task_timings(
        plan.get("tasks", []),
        free_gaps,
        events,
    )

    # Ask Gemini to fix the plan once if validation fails.
    if validation_errors:
        correction_prompt = f"""
    You generated a task plan, but its timings failed validation.

    USER GOAL:
    {goal}

    CURRENT PLAN:
    {json.dumps(plan, indent=2)}

    VALIDATION ERRORS:
    {json.dumps(validation_errors, indent=2)}

    AVAILABLE CANDIDATE WORK WINDOWS:
    {gaps_context}

    CALENDAR EVENTS:
    {calendar_context}

    Revise the plan to fix every validation error.
    Follow these rules:
    - Use only the candidate work windows provided.
    - Never overlap a calendar commitment or another task.
    - Every scheduled task must fit completely within one candidate window.
    - estimated_duration_minutes must be a positive integer.
    - Scheduled duration must match estimated_duration_minutes.
    - Use timezone-aware ISO 8601 timestamps.
    - If a task cannot be scheduled, set both suggested_start and
    suggested_end to null and explain why in its description.
    - Preserve the user's goal and task details where possible.

    Return only a valid JSON object with the same structure as the
    original plan. Do not include Markdown fences or extra commentary.
    """

        correction_response = client.models.generate_content(model=MODEL,contents=correction_prompt,config={"response_mime_type": "application/json"},)
        corrected_plan = json.loads(correction_response.text)

        
    # Validate dependency names and check for circular dependencies.
    tasks = plan.get("tasks", [])
    dependency_errors = validate_dependencies(tasks)

    if dependency_errors:
        plan["validation_errors"] = dependency_errors
        plan["tasks"] = calculate_priority_scores(tasks)
        return plan

    # Convert Google Calendar's nested event format into the flat format
    # expected by the dependency scheduler. Ignore all-day events here;
    # the free gaps are already calculated by the calendar tool.
    scheduler_events = []

    for event in events:
        start_value = event.get("start", {}).get("dateTime")
        end_value = event.get("end", {}).get("dateTime")

        if start_value and end_value:
            scheduler_events.append({
                "start": start_value,
                "end": end_value,
            })

    # Schedule tasks in prerequisite order, using only calculated free gaps.
    scheduled_tasks, scheduling_errors = schedule_tasks_by_dependencies(
        tasks=tasks,
        candidate_windows=free_gaps,
        events=scheduler_events,
    )

    # Validate the resulting timings against calendar gaps and events.
    timing_errors = validate_task_timings(
        scheduled_tasks,
        free_gaps,
        events,
    )

    # Keep the errors visible in the dashboard.
    plan["validation_errors"] = list(dict.fromkeys(
        dependency_errors + scheduling_errors + timing_errors
    ))

    # Recalculate scores and preserve the scheduler's dependency order.
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
