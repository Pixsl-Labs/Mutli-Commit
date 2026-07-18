"""Local issue/workstream helpers for DevWise.

Issues are local-only project planning records.
They do not depend on GitHub/GitLab and they do not modify project files.
"""
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

try:
    from core import settings
    CONFIG_DIR = Path(getattr(settings, "CONFIG_DIR", Path.home() / ".config" / "multi-commit"))
except Exception:
    CONFIG_DIR = Path.home() / ".config" / "multi-commit"

ISSUES_FILE = CONFIG_DIR / "issues.json"


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _project_key(project_path):
    return os.path.abspath(os.path.expanduser(project_path or ""))


def _load_all():
    if not ISSUES_FILE.exists():
        return {"projects": {}}
    try:
        with open(ISSUES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return {"projects": {}}
        data.setdefault("projects", {})
        return data
    except Exception:
        return {"projects": {}}


def _save_all(data):
    ISSUES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ISSUES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _project_bucket(data, project_path):
    key = _project_key(project_path)
    projects = data.setdefault("projects", {})
    return projects.setdefault(key, {"active_issue_id": None, "issues": []})


def slugify(text, prefix="feat"):
    text = str(text or "issue").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    text = text[:52] or "issue"
    return f"{prefix}/{text}"


def list_issues(project_path):
    data = _load_all()
    bucket = _project_bucket(data, project_path)
    return bucket.get("issues", [])


def get_issue(project_path, issue_id):
    for issue in list_issues(project_path):
        if issue.get("id") == issue_id:
            return issue
    return None


def active_issue(project_path):
    data = _load_all()
    bucket = _project_bucket(data, project_path)
    issue_id = bucket.get("active_issue_id")
    return get_issue(project_path, issue_id) if issue_id else None


def set_active_issue(project_path, issue_id):
    data = _load_all()
    bucket = _project_bucket(data, project_path)
    bucket["active_issue_id"] = issue_id
    _save_all(data)
    return get_issue(project_path, issue_id)


def create_issue(project_path, title, branch=None, tasks=None, source="manual"):
    data = _load_all()
    bucket = _project_bucket(data, project_path)

    title = str(title or "Untitled issue").strip() or "Untitled issue"
    issue = {
        "id": str(uuid.uuid4()),
        "title": title,
        "branch": branch or slugify(title),
        "status": "open",
        "source": source,
        "tasks": tasks or [],
        "created": _now(),
        "updated": _now(),
    }

    bucket.setdefault("issues", []).append(issue)
    bucket["active_issue_id"] = issue["id"]
    _save_all(data)
    return issue


def update_issue(project_path, issue_id, **fields):
    data = _load_all()
    bucket = _project_bucket(data, project_path)

    for issue in bucket.get("issues", []):
        if issue.get("id") == issue_id:
            issue.update(fields)
            issue["updated"] = _now()
            _save_all(data)
            return issue

    return None


def close_issue(project_path, issue_id):
    return update_issue(project_path, issue_id, status="closed")


def reopen_issue(project_path, issue_id):
    return update_issue(project_path, issue_id, status="open")
