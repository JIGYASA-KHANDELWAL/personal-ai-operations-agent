
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"

# Read-only permission: this cannot create or change events.
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]


def get_calendar_service():
    credentials = None

    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(
            str(TOKEN_FILE), SCOPES
        )

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials or not credentials.valid:
        if not CREDENTIALS_FILE.exists():
            raise FileNotFoundError(
                f"OAuth credentials not found: {CREDENTIALS_FILE}"
            )

        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE), SCOPES
        )

        credentials = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(credentials.to_json())
        TOKEN_FILE.chmod(0o600)

    return build("calendar", "v3", credentials=credentials)



def get_upcoming_events(max_results=100):
    service = get_calendar_service()

    now = datetime.now(timezone.utc)
    end_of_week = now + timedelta(days=7)

    result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=end_of_week.isoformat(),
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    return result.get("items", [])




def calculate_free_gaps(
    events,
    start_date=None,
    days=7,
    day_start_hour=9,
    day_end_hour=20,
):
    """
    Calculate candidate work windows across a date range,
    subtracting timed calendar commitments.
    """
    from datetime import date, datetime, time, timedelta, timezone

    if start_date is None:
        start_date = datetime.now().date()
    elif isinstance(start_date, datetime):
        start_date = start_date.date()

    parsed_events = []

    for event in events:
        start = event.get("start", {})
        end = event.get("end", {})

        start_value = start.get("dateTime")
        end_value = end.get("dateTime")

        # Skip all-day events for now.
        if not start_value or not end_value:
            continue

        try:
            start_dt = datetime.fromisoformat(
                start_value.replace("Z", "+00:00")
            )
            end_dt = datetime.fromisoformat(
                end_value.replace("Z", "+00:00")
            )
        except ValueError:
            continue

        if end_dt > start_dt:
            parsed_events.append((start_dt, end_dt))

    # Use the first event's timezone, or the local timezone
    # if the calendar contains no timed events.
    if parsed_events:
        tz = parsed_events[0][0].tzinfo
    else:
        tz = datetime.now().astimezone().tzinfo

    # Normalize event times to the same timezone.
    parsed_events = [
        (start.astimezone(tz), end.astimezone(tz))
        for start, end in parsed_events
    ]

    gaps = []

    for day_offset in range(days):
        current_date = start_date + timedelta(days=day_offset)

        day_start = datetime.combine(
            current_date,
            time(day_start_hour, 0),
            tzinfo=tz,
        )
        day_end = datetime.combine(
            current_date,
            time(day_end_hour, 0),
            tzinfo=tz,
        )

        day_events = []

        for start_dt, end_dt in parsed_events:
            clipped_start = max(start_dt, day_start)
            clipped_end = min(end_dt, day_end)

            if clipped_start < clipped_end:
                day_events.append((clipped_start, clipped_end))

        # Merge overlapping or adjacent commitments.
        merged_events = []

        for start_dt, end_dt in sorted(day_events):
            if (
                merged_events
                and start_dt <= merged_events[-1][1]
            ):
                previous_start, previous_end = merged_events[-1]
                merged_events[-1] = (
                    previous_start,
                    max(previous_end, end_dt),
                )
            else:
                merged_events.append((start_dt, end_dt))

        cursor = day_start

        for start_dt, end_dt in merged_events:
            if start_dt > cursor:
                minutes = int(
                    (start_dt - cursor).total_seconds() // 60
                )
                gaps.append({
                    "start": cursor.isoformat(),
                    "end": start_dt.isoformat(),
                    "duration_minutes": minutes,
                })

            cursor = max(cursor, end_dt)

        # Include the time after the last event, or the full
        # planning window when there are no events that day.
        if cursor < day_end:
            minutes = int(
                (day_end - cursor).total_seconds() // 60
            )
            gaps.append({
                "start": cursor.isoformat(),
                "end": day_end.isoformat(),
                "duration_minutes": minutes,
            })

    return gaps



if __name__ == "__main__":
    events = get_upcoming_events()

    if not events:
        print("No upcoming events found.")
    else:
        print("\n--- UPCOMING CALENDAR EVENTS ---\n")

        for event in events:
            start = event.get("start", {})
            start_time = start.get("dateTime", start.get("date", "Unknown"))
            print(f"{start_time} | {event.get('summary', '(No title)')}")
