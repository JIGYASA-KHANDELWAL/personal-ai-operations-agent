
from datetime import datetime
from app.agents.planner import calculate_priority_scores

fixed_now = datetime.fromisoformat("2026-10-17T12:00:00+05:30")

tasks = [
    {
        "task": "Secure venue",
        "importance": 5,
        "deadline": "2026-10-18T12:00:00+05:30",
        "depends_on": [],
    },
    {
        "task": "Create promotional posters",
        "importance": 3,
        "deadline": None,
        "depends_on": ["Secure venue"],
    },
    {
        "task": "Choose event theme",
        "importance": 2,
        "deadline": None,
        "depends_on": [],
    },
]

ranked = calculate_priority_scores(tasks, now=fixed_now)
ranked.sort(key=lambda task: task["priority_score"], reverse=True)

for task in ranked:
    print(
        f"{task['priority_score']:6.2f} | "
        f"{task['computed_priority']:6} | "
        f"{task['task']}"
    )

assert all(0 <= task["priority_score"] <= 100 for task in ranked)
assert len({task["task"] for task in ranked}) == len(tasks)
assert ranked[0]["task"] == "Secure venue"

print("\nPriority scoring tests passed.")
