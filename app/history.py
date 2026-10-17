
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from database import initialize_database, get_recent_plans


def show_history():
    initialize_database()
    plans = get_recent_plans(limit=10)

    if not plans:
        print("No saved plans found.")
        return

    print("\n===== YOUR SAVED PLANS =====")

    for plan in plans:
        print(f"\nPlan ID: {plan['id']}")
        print(f"Goal: {plan['goal']}")
        print(f"Created: {plan['created_at']}")

        tasks = json.loads(plan["tasks_json"])

        for number, task in enumerate(tasks, start=1):
            print(
                f"  {number}. {task['task']} "
                f"[Priority: {task['priority']}]"
            )


if __name__ == "__main__":
    show_history()
