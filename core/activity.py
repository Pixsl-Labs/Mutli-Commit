"""Activity log and project metrics for Multi-Commit.

Stored in ~/.config/multi-commit/activity.json
"""
import json
import os
from datetime import datetime, timedelta

CONFIG_DIR = os.path.expanduser("~/.config/multi-commit")
ACTIVITY_FILE = os.path.join(CONFIG_DIR, "activity.json")


def _ensure():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _norm(path):
    if not path:
        return ""
    return os.path.abspath(os.path.expanduser(path))


def load_all():
    _ensure()
    if not os.path.exists(ACTIVITY_FILE):
        return []
    try:
        with open(ACTIVITY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_all(events):
    _ensure()
    with open(ACTIVITY_FILE, "w", encoding="utf-8") as f:
        json.dump(events[-2000:], f, indent=2)


def log_event(project_path, event_type, message, meta=None):
    events = load_all()
    event = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "project_path": _norm(project_path),
        "project_name": os.path.basename(_norm(project_path)) if project_path else "",
        "type": event_type,
        "message": message,
        "meta": meta or {},
    }
    events.append(event)
    save_all(events)
    return event


def recent(project_path=None, limit=12):
    events = load_all()
    key = _norm(project_path) if project_path else None

    if key:
        events = [e for e in events if e.get("project_path") == key]

    return list(reversed(events[-limit:]))


def metrics(project_path=None, days=7):
    events = load_all()
    key = _norm(project_path) if project_path else None
    cutoff = datetime.now() - timedelta(days=days)

    counts = {
        "commits": 0,
        "pushes": 0,
        "commands": 0,
        "checklists": 0,
        "code_reviews": 0,
        "config_backups": 0,
        "updates": 0,
    }

    for event in events:
        if key and event.get("project_path") != key:
            continue

        try:
            ts = datetime.fromisoformat(event.get("timestamp", ""))
            if ts < cutoff:
                continue
        except Exception:
            continue

        etype = event.get("type", "")

        if etype.startswith("commit"):
            counts["commits"] += 1
        elif etype.startswith("push"):
            counts["pushes"] += 1
        elif etype.startswith("command"):
            counts["commands"] += 1
        elif etype.startswith("checklist"):
            counts["checklists"] += 1
        elif etype.startswith("code_review"):
            counts["code_reviews"] += 1
        elif etype.startswith("config"):
            counts["config_backups"] += 1
        elif etype.startswith("update"):
            counts["updates"] += 1

    return counts


def clear(project_path=None):
    if not project_path:
        save_all([])
        return

    key = _norm(project_path)
    events = [e for e in load_all() if e.get("project_path") != key]
    save_all(events)

# ── Dashboard helpers ───────────────────────────────────────────────────────

def summary_text(project_path=None, days=7):
    """Return a compact text summary for dashboard display."""
    m = metrics(project_path, days=days)
    return (
        f"Last {days} days:\n"
        f"Commits: {m.get('commits', 0)}\n"
        f"Pushes: {m.get('pushes', 0)}\n"
        f"Commands: {m.get('commands', 0)}\n"
        f"Checklists: {m.get('checklists', 0)}\n"
        f"Code reviews: {m.get('code_reviews', 0)}\n"
        f"Backups/updates: {m.get('config_backups', 0)} / {m.get('updates', 0)}"
    )


def log_code_review(project_path, output_path):
    return log_event(project_path, "code_review_generated", f"Generated code review: {output_path}")


def log_config_backup(output_path):
    return log_event("", "config_backup_exported", f"Exported config backup: {output_path}")
