# Personal AI Operations Agent — Operations Center upgrade

## Added
- `app/agents/operations_center.py`: task risk analysis, portfolio progress aggregation, and calendar-aware rescheduling preview.
- `app/main.py`: Operations Center dashboard integrated with existing task tracking and saved plans.

## Safety behavior
- Rescheduling is preview-only. It does not write to Google Calendar.
- Completed tasks are excluded from the proposed reschedule.
- Existing saved task data is not overwritten by the preview.

## Apply
1. Stop Streamlit with Ctrl+C.
2. Back up your current project folder.
3. Copy the included `app/` folder over the project's `app/` folder.
4. Run: `python -m streamlit run app/main.py`

## Notes
The ZIP uploaded for review did not contain `requirements.txt` or the test suite, so this bundle preserves your existing dependency setup and does not claim the full test suite was run. Python compilation checks passed for the included app files.
