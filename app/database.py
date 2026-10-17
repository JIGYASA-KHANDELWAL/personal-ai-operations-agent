
import json
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "agent.db"

TASK_STATUSES = ["Pending", "In Progress", "Completed", "Blocked"]


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database():
    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                goal TEXT NOT NULL,
                tasks_json TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS task_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                task_index INTEGER NOT NULL,
                task_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                notes TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(plan_id, task_index),
                FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS execution_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                plan_id INTEGER NOT NULL,
                task_index INTEGER NOT NULL,
                task_name TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(plan_id) REFERENCES plans(id) ON DELETE CASCADE
            )
        """)


def save_plan(goal, tasks):
    with get_connection() as connection:
        cursor = connection.execute(
            "INSERT INTO plans (goal, tasks_json) VALUES (?, ?)",
            (goal, json.dumps(tasks, ensure_ascii=False))
        )
        plan_id = cursor.lastrowid

        for index, task in enumerate(tasks):
            connection.execute("""
                INSERT INTO task_tracking
                    (plan_id, task_index, task_name, status)
                VALUES (?, ?, ?, 'Pending')
            """, (plan_id, index, task.get("task", f"Task {index + 1}")))

        return plan_id


def get_recent_plans(limit=10):
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT id, goal, tasks_json, created_at "
            "FROM plans ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def ensure_task_tracking(plan_id, tasks):
    """Create missing tracking rows for older saved plans."""
    with get_connection() as connection:
        for index, task in enumerate(tasks):
            connection.execute("""
                INSERT OR IGNORE INTO task_tracking
                    (plan_id, task_index, task_name, status)
                VALUES (?, ?, ?, 'Pending')
            """, (
                plan_id,
                index,
                task.get("task", f"Task {index + 1}")
            ))


def get_task_tracking(plan_id):
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT task_index, task_name, status, notes, updated_at
            FROM task_tracking
            WHERE plan_id = ?
            ORDER BY task_index
        """, (plan_id,)).fetchall()

        return {row["task_index"]: dict(row) for row in rows}


def update_task_tracking(plan_id, task_index, task_name, status, notes=""):
    if status not in TASK_STATUSES:
        raise ValueError(f"Invalid task status: {status}")

    with get_connection() as connection:
        existing = connection.execute("""
            SELECT status, notes FROM task_tracking
            WHERE plan_id = ? AND task_index = ?
        """, (plan_id, task_index)).fetchone()

        old_status = existing["status"] if existing else None
        old_notes = existing["notes"] if existing else ""

        connection.execute("""
            INSERT INTO task_tracking
                (plan_id, task_index, task_name, status, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(plan_id, task_index) DO UPDATE SET
                task_name = excluded.task_name,
                status = excluded.status,
                notes = excluded.notes,
                updated_at = CURRENT_TIMESTAMP
        """, (plan_id, task_index, task_name, status, notes))

        # Log meaningful changes only.
        if old_status != status or old_notes != notes:
            connection.execute("""
                INSERT INTO execution_log
                    (plan_id, task_index, task_name, old_status,
                     new_status, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                plan_id,
                task_index,
                task_name,
                old_status,
                status,
                notes
            ))


def get_plan_progress(plan_id):
    with get_connection() as connection:
        row = connection.execute("""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN status = 'In Progress' THEN 1 ELSE 0 END) AS in_progress,
                SUM(CASE WHEN status = 'Blocked' THEN 1 ELSE 0 END) AS blocked
            FROM task_tracking
            WHERE plan_id = ?
        """, (plan_id,)).fetchone()

        total = row["total"] or 0
        completed = row["completed"] or 0
        in_progress = row["in_progress"] or 0
        blocked = row["blocked"] or 0

        return {
            "total": total,
            "completed": completed,
            "in_progress": in_progress,
            "blocked": blocked,
            "pending": total - completed - in_progress - blocked,
            "percentage": round(completed / total * 100, 1) if total else 0
        }


def get_execution_log(plan_id, limit=50):
    with get_connection() as connection:
        rows = connection.execute("""
            SELECT task_name, old_status, new_status, notes, created_at
            FROM execution_log
            WHERE plan_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (plan_id, limit)).fetchall()

        return [dict(row) for row in rows]


if __name__ == "__main__":
    initialize_database()
    print(f"Database initialized at: {DB_PATH}")
