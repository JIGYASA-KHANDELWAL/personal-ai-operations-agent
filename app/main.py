from agents.email_assistant import draft_email
from agents.document_generator import generate_document
from tools.calendar_tool import get_upcoming_events
from io import BytesIO
import streamlit as st
import json
import sys
from pathlib import Path

from agents.daily_assistant import build_daily_briefing
from agents.operations_center import analyze_operations, summarize_portfolio, propose_reschedule

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from agents.planner import create_plan
from database import (initialize_database,save_plan,get_recent_plans,get_task_tracking,update_task_tracking,get_plan_progress ,get_execution_log,ensure_task_tracking,TASK_STATUSES,)
st.set_page_config(
    page_title="Personal AI Operations Agent",
    page_icon="🤖",
    layout="wide"
)

initialize_database()

st.title("🤖 Personal AI Operations Agent")
st.write("Turn your goals into clear, prioritized action plans.")
st.divider()
st.subheader("Create a new plan")

goal = st.text_area(
    "What would you like to accomplish?",
    placeholder="Example: Organize a technical workshop for college students",
    height=100
)

if st.button("✨ Generate Plan", type="primary"):
    if not goal.strip():
        st.warning("Please enter a goal first.")
    else:
        with st.spinner("Your AI planner is creating a plan..."):
            try:
                plan = create_plan(goal.strip())
                plan_id = save_plan(goal.strip(), plan["tasks"])
                if plan.get("validation_errors"):
                    st.error("The plan still contains scheduling conflicts.")
                    for error in plan["validation_errors"]:
                        st.write(f"- {error}")
                    st.info("Review these tasks before relying on their suggested timings.")
                else:
                    st.success("All proposed task timings passed validation.")
                st.session_state["latest_plan"] = plan
                st.session_state["latest_plan_id"] = plan_id

            except Exception as error:
                st.error(f"Could not generate the plan: {error}")



if "latest_plan" in st.session_state:
    plan = st.session_state["latest_plan"]

    st.subheader("Your Action Plan")
    st.caption(f"Saved plan ID: {st.session_state['latest_plan_id']}")

    ranked_tasks = sorted(
        plan["tasks"],
        key=lambda task: task.get("priority_score", 0),
        reverse=True,
    )

    for number, task in enumerate(ranked_tasks, start=1):
        with st.container(border=True):
            st.markdown(f"**{number}. {task['task']}**")

            priority = task.get(
                "computed_priority",
                task.get("priority", "Medium"),
            )

            st.write(f"**Calculated priority:** {priority}")
            st.metric(
                "Priority score",
                f"{task.get('priority_score', 0):.2f}/100",
            )
            st.write(f"Importance: {task.get('importance', 3)}/5")
            st.write(task.get("description", ""))

            deadline = task.get("deadline")
            st.write(f"Deadline: {deadline or 'Not specified'}")

            duration = task.get("estimated_duration_minutes")
            if duration is not None:
                st.write(f"Estimated duration: {duration} minutes")

            start = task.get("suggested_start")
            end = task.get("suggested_end")

            if start and end:
                st.write(f"Suggested time: {start} to {end}")
            else:
                st.write("Suggested time: Not scheduled")

            dependencies = task.get("depends_on", [])
            if dependencies:
                st.write("Depends on: " + ", ".join(dependencies))

            reason = task.get("priority_reason")
            if reason:
                st.write(f"**Why this priority?** {reason}")

    validation_errors = plan.get("validation_errors", [])
    if validation_errors:
        st.error("Some task timings still need attention.")
        for error in validation_errors:
            st.write(f"- {error}")
    else:
        st.success("All proposed task timings passed validation.")


# PASTE THE COMPLETE TASK EXECUTION DASHBOARD SECTION HERE

# --------------------------------------------------
# Task Execution, Historical Plans, and Execution Log
# --------------------------------------------------

st.divider()
st.header("✅ Task Execution & Progress")

tracking_plans = get_recent_plans(limit=100)

if not tracking_plans:
    st.info("Generate a plan to start tracking task execution.")
else:
    plan_options = {
        f"Plan #{item['id']} — {item['goal']}": item
        for item in tracking_plans
    }

    default_label = next(
        (
            label for label, item in plan_options.items()
            if item["id"] == st.session_state.get("latest_plan_id")
        ),
        next(iter(plan_options))
    )

    selected_tracking_label = st.selectbox(
        "Choose a plan to track",
        list(plan_options.keys()),
        index=list(plan_options.keys()).index(default_label),
        key="tracking_plan_selector",
    )

    selected_tracking_plan = plan_options[selected_tracking_label]
    tracking_plan_id = selected_tracking_plan["id"]
    tracking_tasks = json.loads(selected_tracking_plan["tasks_json"])

    ensure_task_tracking(tracking_plan_id, tracking_tasks)
    tracking = get_task_tracking(tracking_plan_id)
    progress = get_plan_progress(tracking_plan_id)

    st.subheader(selected_tracking_plan["goal"])

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total", progress["total"])
    col2.metric("Completed", progress["completed"])
    col3.metric("In Progress", progress["in_progress"])
    col4.metric("Blocked", progress["blocked"])

    st.progress(progress["percentage"] / 100)
    st.caption(
        f"{progress['percentage']}% complete · "
        f"{progress['pending']} pending"
    )

    for index, task in enumerate(tracking_tasks):
        task_name = task.get("task", f"Task {index + 1}")
        saved = tracking.get(index, {})
        current_status = saved.get("status", "Pending")
        current_notes = saved.get("notes", "")

        with st.container(border=True):
            st.markdown(f"**{index + 1}. {task_name}**")

            status = st.selectbox(
                "Status",
                TASK_STATUSES,
                index=(
                    TASK_STATUSES.index(current_status)
                    if current_status in TASK_STATUSES else 0
                ),
                key=f"track_status_{tracking_plan_id}_{index}",
            )

            notes = st.text_area(
                "Progress notes / blockers",
                value=current_notes,
                placeholder="Record progress, next steps, or blockers...",
                key=f"track_notes_{tracking_plan_id}_{index}",
            )

            if st.button(
                "Save Update",
                key=f"track_save_{tracking_plan_id}_{index}",
            ):
                update_task_tracking(
                    plan_id=tracking_plan_id,
                    task_index=index,
                    task_name=task_name,
                    status=status,
                    notes=notes.strip(),
                )
                st.success("Task update saved.")
                st.rerun()

            if saved.get("updated_at"):
                st.caption(f"Last saved: {saved['updated_at']}")

    st.subheader("📜 Execution History")

    history = get_execution_log(tracking_plan_id, limit=50)

    if not history:
        st.info("No task updates have been recorded for this plan yet.")
    else:
        for entry in history:
            previous = entry["old_status"] or "Not recorded"

            with st.container(border=True):
                st.markdown(f"**{entry['task_name']}**")
                st.write(
                    f"{previous} → {entry['new_status']}"
                )
                st.caption(entry["created_at"])

                if entry["notes"]:
                    st.write(entry["notes"])



# --------------------------------------------------
# Daily Focus Assistant
# --------------------------------------------------

st.divider()
st.header("☀️ Daily Focus Assistant")
st.caption(
    "Recommendations based on saved task status, priority, "
    "deadlines, and upcoming calendar events."
)

daily_plans = get_recent_plans(limit=100)

if not daily_plans:
    st.info("Generate a plan first to receive daily recommendations.")
else:
    daily_options = {
        f"Plan #{item['id']} — {item['goal']}": item
        for item in daily_plans
    }

    daily_label = st.selectbox(
        "Choose a plan for your daily briefing",
        list(daily_options.keys()),
        key="daily_focus_plan",
    )

    daily_plan = daily_options[daily_label]
    daily_tasks = json.loads(daily_plan["tasks_json"])

    ensure_task_tracking(daily_plan["id"], daily_tasks)
    daily_tracking = get_task_tracking(daily_plan["id"])

    calendar_events = st.session_state.get("calendar_events", [])

    if st.button("🔎 Generate Daily Briefing", type="primary"):
        briefing = build_daily_briefing(
            daily_tasks,
            daily_tracking,
            calendar_events,
        )
        st.session_state["daily_briefing"] = briefing
        st.session_state["daily_briefing_plan_id"] = daily_plan["id"]

    briefing = st.session_state.get("daily_briefing")
    briefing_plan_id = st.session_state.get("daily_briefing_plan_id")

    if briefing and briefing_plan_id == daily_plan["id"]:
        st.subheader("Your Focus Summary")

        c1, c2, c3 = st.columns(3)
        c1.metric("Completed", briefing["completed"])
        c2.metric("Remaining", len(briefing["actions"]))
        c3.metric("Blocked", len(briefing["blockers"]))

        st.progress(
            briefing["completed"] / briefing["total"]
            if briefing["total"] else 0
        )

        if briefing["blockers"]:
            st.subheader("🚧 Blockers to Resolve")
            for item in briefing["blockers"]:
                st.warning(
                    f"**{item['task']}**\n\n"
                    f"{item['notes'] or 'No blocker notes recorded.'}"
                )

        st.subheader("🎯 Recommended Next Actions")

        if not briefing["actions"]:
            st.success("All tasks in this plan are completed or blocked.")
        else:
            for number, item in enumerate(briefing["actions"], start=1):
                with st.container(border=True):
                    st.markdown(f"**{number}. {item['task']}**")
                    st.write(f"Status: {item['status']}")
                    st.write(f"Priority score: {item['score']}/100")
                    st.write(f"Estimated effort: {item['duration']} minutes")
                    st.write(f"Reason: {item['reason']}")

                    if item["deadline"]:
                        st.write(
                            "Deadline: "
                            + item["deadline"].strftime("%d %b %Y, %I:%M %p")
                        )

                    if item["suggested_start"] and item["suggested_end"]:
                        st.write(
                            "Previously scheduled: "
                            f"{item['suggested_start']} to "
                            f"{item['suggested_end']}"
                        )

        st.subheader("📅 Upcoming Calendar Events")

        if briefing["upcoming_events"]:
            for event in briefing["upcoming_events"][:10]:
                st.write(
                    f"- **{event['start'].strftime('%d %b, %I:%M %p')}** "
                    f"— {event['title']}"
                )
        else:
            st.info(
                "No upcoming events are loaded. Use Refresh Calendar "
                "in the Google Calendar section."
            )

st.divider()

st.divider()
st.header("🧭 Operations Center")
st.caption("Risk detection, portfolio analytics, and rescheduling previews. This section never edits Google Calendar.")

ops_plans = get_recent_plans(limit=100)
if ops_plans:
    portfolio = summarize_portfolio(ops_plans, get_task_tracking)
    st.subheader("📊 Portfolio Analytics")
    cols = st.columns(5)
    for col, label, value in zip(cols, ["Plans", "Tasks", "Completed", "Blocked", "Overall completion"], [portfolio["plans"], portfolio["total_tasks"], portfolio["completed"], portfolio["blocked"], f'{portfolio["percentage"]}%']):
        col.metric(label, value)
    st.progress(portfolio["percentage"] / 100 if portfolio["total_tasks"] else 0)
    with st.expander("Progress by plan", expanded=True):
        st.dataframe([{"Plan": f'#{r["id"]}', "Goal": r["goal"], "Tasks": r["total"], "Completed": r["completed"], "In progress": r["in_progress"], "Blocked": r["blocked"], "Completion %": r["percentage"], "Created": r["created_at"]} for r in portfolio["plan_rows"]], use_container_width=True, hide_index=True)

    options = {f'Plan #{p["id"]} — {p["goal"]}': p for p in ops_plans}
    selected = st.selectbox("Plan to inspect or reschedule", list(options.keys()), key="operations_plan_selector")
    chosen = options[selected]
    tasks = json.loads(chosen["tasks_json"])
    ensure_task_tracking(chosen["id"], tasks)
    tracking = get_task_tracking(chosen["id"])

    st.subheader("🚦 Execution Risks")
    findings = analyze_operations(tasks, tracking)
    if not findings:
        st.success("No outstanding risks detected by the current rules.")
    for finding in findings:
        with st.container(border=True):
            st.markdown(f'**[{finding["severity"]}] {finding["task"]}**')
            st.write(" · ".join(finding["reasons"]))
            if finding.get("deadline"):
                st.caption(f'Deadline: {finding["deadline"]}')

    st.subheader("🗓️ Smart Rescheduling Preview")
    st.write("Proposes new times using calendar gaps and task dependencies. Completed tasks are excluded. The saved plan and calendar are not changed.")
    if st.button("Build rescheduling preview", key="build_reschedule_preview"):
        try:
            st.session_state["reschedule_preview"] = propose_reschedule(tasks, tracking, st.session_state.get("calendar_events", []))
            st.session_state["reschedule_preview_plan_id"] = chosen["id"]
        except Exception as error:
            st.error(f"Could not create a preview: {error}")
    preview = st.session_state.get("reschedule_preview")
    if preview and st.session_state.get("reschedule_preview_plan_id") == chosen["id"]:
        st.info(preview["message"])
        if preview["completed_unchanged"]:
            st.write("Completed tasks left untouched: " + ", ".join(preview["completed_unchanged"]))
        st.dataframe([{"Task": t.get("task"), "Duration (min)": t.get("estimated_duration_minutes"), "Proposed start": t.get("suggested_start") or "Unscheduled", "Proposed end": t.get("suggested_end") or "Unscheduled", "Dependencies": ", ".join(t.get("depends_on", []) or [])} for t in preview["tasks"]], use_container_width=True, hide_index=True)
        if preview["errors"]:
            st.warning("Some tasks need attention:")
            for error in preview["errors"]:
                st.write(f"- {error}")
else:
    st.info("Save a plan to see portfolio analytics and execution risks.")

st.subheader("Saved Plan History")
plans = get_recent_plans(limit=10)

if not plans:
    st.info("Your saved plans will appear here.")
else:
    for saved_plan in plans:
        with st.expander(
            f"Plan #{saved_plan['id']} — {saved_plan['goal']}"
        ):
            st.caption(f"Created: {saved_plan['created_at']}")

            tasks = json.loads(saved_plan["tasks_json"])

            ranked_tasks = sorted(
                tasks,
                key=lambda task: task.get("priority_score", 0),
                reverse=True,
            )

            for number, task in enumerate(ranked_tasks, start=1):
                priority = task.get(
                    "computed_priority",
                    task.get("priority", "Medium"),
                )

                st.markdown(f"**{number}. {task['task']}**")
                st.write(f"Calculated priority: {priority}")
                st.write(
                    f"Priority score: "
                    f"{task.get('priority_score', 0):.2f}/100"
                )
                st.write(f"Importance: {task.get('importance', 3)}/5")
                st.write(task.get("description", ""))

                st.write(
                    f"Deadline: {task.get('deadline') or 'Not specified'}"
                )

                duration = task.get("estimated_duration_minutes")
                if duration is not None:
                    st.write(f"Estimated duration: {duration} minutes")

                start = task.get("suggested_start")
                end = task.get("suggested_end")

                if start and end:
                    st.write(f"Suggested time: {start} to {end}")
                else:
                    st.write("Suggested time: Not scheduled")

                dependencies = task.get("depends_on", [])
                if dependencies:
                    st.write("Depends on: " + ", ".join(dependencies))

                reason = task.get("priority_reason")
                if reason:
                    st.write(f"Why this priority? {reason}")

st.divider()
st.subheader("Export an Action Plan")

saved_plans = get_recent_plans(limit=10)

if saved_plans:
    plan_options = {
        f"Plan #{p['id']} — {p['goal']}": p
        for p in saved_plans
    }

    selected_label = st.selectbox(
        "Choose a saved plan",
        list(plan_options.keys())
    )

    selected_plan = plan_options[selected_label]

    if st.button("Generate Word Document"):
        tasks = json.loads(selected_plan["tasks_json"])

        document = generate_document(
            selected_plan["goal"],
            tasks
        )

        file_buffer = BytesIO()
        document.save(file_buffer)
        file_buffer.seek(0)

        filename = f"action_plan_{selected_plan['id']}.docx"

        st.download_button(
            label="Download Word Document",
            data=file_buffer.getvalue(),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
else:
    st.info("Generate and save a plan before exporting it.")


st.divider()
st.header("✉️ Email Assistant")

st.write("Draft professional emails with the help of Gemini.")

with st.form("email_draft_form"):
    email_purpose = st.text_area(
        "What should the email be about?",
        placeholder="Invite a guest speaker to a college technical workshop"
    )

    email_recipient = st.text_input(
        "Who is the recipient?",
        placeholder="Guest speaker"
    )

    email_tone = st.selectbox(
        "Email tone",
        ["Professional", "Formal", "Friendly", "Concise"]
    )

    generate_email = st.form_submit_button("Generate Email Draft")

if generate_email:
    if not email_purpose.strip() or not email_recipient.strip():
        st.warning("Please enter the email purpose and recipient.")
    else:
        with st.spinner("Drafting your email..."):
            try:
                email_result = draft_email(
                    email_purpose.strip(),
                    email_recipient.strip(),
                    email_tone
                )

                st.session_state["email_draft"] = email_result

            except Exception as error:
                st.error(f"Could not draft the email: {error}")

if "email_draft" in st.session_state:
    st.subheader("Your Email Draft")

    edited_draft = st.text_area(
        "Review and edit before using",
        value=st.session_state["email_draft"],
        height=300,
        key="editable_email_draft"
    )

    st.download_button(
        "Download Email Draft",
        data=edited_draft,
        file_name="email_draft.txt",
        mime="text/plain"
    )


st.divider()
st.header("📅 Google Calendar")

st.write("View your upcoming Google Calendar events.")

if st.button("🔄 Refresh Calendar"):
    try:
        with st.spinner("Fetching your upcoming events..."):
            events = get_upcoming_events(max_results=10)
            st.session_state["calendar_events"] = events
            st.session_state["calendar_loaded"] = True
    except Exception as error:
        st.error(f"Could not load calendar events: {error}")

if "calendar_loaded" not in st.session_state:
    try:
        with st.spinner("Loading your calendar..."):
            events = get_upcoming_events(max_results=10)
            st.session_state["calendar_events"] = events
            st.session_state["calendar_loaded"] = True
    except Exception as error:
        st.error(f"Could not load calendar events: {error}")

if st.session_state.get("calendar_loaded"):
    events = st.session_state.get("calendar_events", [])

    if not events:
        st.info("No upcoming events found.")
    else:
        st.success(f"Found {len(events)} upcoming event(s).")

        for event in events:
            start = event.get("start", {})
            start_time = start.get(
                "dateTime",
                start.get("date", "Time not specified")
            )

            with st.container(border=True):
                st.markdown(
                    f"**{event.get('summary', '(No title)')}**"
                )
                st.write(f"Start: {start_time}")

                location = event.get("location")
                if location:
                    st.write(f"Location: {location}")

                description = event.get("description")
                if description:
                    st.write(description)
