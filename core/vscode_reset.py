"""Reset VSCode workspace/session state for a project.

This is intentionally safe:
- It does NOT delete project files.
- It does NOT edit Git.
- It only moves matching VSCode workspaceStorage folders into a backup.
"""
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlparse

from core import settings


def _candidate_storage_dirs():
    home = Path.home()
    return [
        home / ".config" / "Code" / "User" / "workspaceStorage",
        home / ".config" / "Code - OSS" / "User" / "workspaceStorage",
        home / ".config" / "VSCodium" / "User" / "workspaceStorage",
    ]


def _normalise_path(value):
    if not value:
        return ""

    value = unquote(str(value))

    if value.startswith("file://"):
        parsed = urlparse(value)
        value = parsed.path

    try:
        return os.path.abspath(os.path.expanduser(value))
    except Exception:
        return value


def _string_matches_project(value, project_path):
    value = unquote(str(value))
    project_path = os.path.abspath(os.path.expanduser(project_path))

    normalised = _normalise_path(value)

    if normalised == project_path:
        return True

    # VSCode sometimes stores URIs or nested file paths. This catches both.
    return project_path in normalised or project_path in value


def _json_contains_project(obj, project_path):
    if isinstance(obj, dict):
        return any(_json_contains_project(v, project_path) for v in obj.values())

    if isinstance(obj, list):
        return any(_json_contains_project(v, project_path) for v in obj)

    if isinstance(obj, str):
        return _string_matches_project(obj, project_path)

    return False


def _workspace_matches_project(workspace_dir, project_path):
    workspace_json = Path(workspace_dir) / "workspace.json"

    if not workspace_json.exists():
        return False

    try:
        data = json.loads(workspace_json.read_text(encoding="utf-8"))
    except Exception:
        return False

    return _json_contains_project(data, project_path)


def find_workspace_state_dirs(project_path):
    matches = []

    for storage_root in _candidate_storage_dirs():
        if not storage_root.exists():
            continue

        for child in storage_root.iterdir():
            if child.is_dir() and _workspace_matches_project(child, project_path):
                matches.append(child)

    return matches


def reset_project_workspace(project_path):
    project_path = os.path.abspath(os.path.expanduser(project_path))
    matches = find_workspace_state_dirs(project_path)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = (
        Path(getattr(settings, "CONFIG_DIR", Path.home() / ".config" / "multi-commit"))
        / "vscode_reset_backups"
        / stamp
    )
    backup_root.mkdir(parents=True, exist_ok=True)

    moved = []

    for workspace_dir in matches:
        destination = backup_root / workspace_dir.name

        try:
            shutil.move(str(workspace_dir), str(destination))
            moved.append(str(destination))
        except Exception:
            continue

    return {
        "ok": True,
        "project_path": project_path,
        "matched": len(matches),
        "moved": moved,
        "backup_root": str(backup_root),
    }


def open_clean_vscode(project_path):
    project_path = os.path.abspath(os.path.expanduser(project_path))
    cmd = settings.get("vscode_cmd") or "code"

    attempts = [
        [cmd, "--new-window", project_path],
        [cmd, project_path],
        ["xdg-open", project_path],
    ]

    for attempt in attempts:
        try:
            subprocess.Popen(attempt)
            return True
        except Exception:
            continue

    return False
