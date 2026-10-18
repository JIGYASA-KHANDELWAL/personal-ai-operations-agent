# LangGraph integration

The app now runs plan generation through `app/agents/workflow_graph.py`:

1. `generate_plan` calls the existing Gemini planner.
2. `validate_and_prepare_review` reads the planner's scheduling validation errors and labels the result `ready_for_user_review` or `needs_review`.
3. The Streamlit UI presents the plan and validation findings.

The existing scheduler, SQLite persistence, task tracking, daily briefing, and Operations Center remain in place. LangGraph orchestrates the workflow; it does not replace deterministic scheduling logic.

## Safety boundaries
- Email generation produces a draft only; no email is sent.
- Google Calendar integration is read-only; no calendar events are created or modified.
- Rescheduling remains a preview; it does not alter saved task timing or calendar data.
- A generated plan is not a claim that tasks have been scheduled in Google Calendar.

## Install / run
From the project root, activate your virtual environment, then run:

```bash
python -m pip install -r requirements.txt
python -m streamlit run app/main.py
```

Keep `.env`, `credentials.json`, `token.json`, `.venv/`, and the local SQLite database out of Git.
