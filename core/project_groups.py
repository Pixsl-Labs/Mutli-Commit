"""Project groups, pinned projects and sidebar organisation.

Stored in ~/.config/multi-commit/project_groups.json.
This layer sits above core/project_manager.py so existing recent projects still work.
"""
import json
import os
import uuid
from core import project_manager

CONFIG_DIR = os.path.expanduser("~/.config/multi-commit")
GROUPS_FILE = os.path.join(CONFIG_DIR, "project_groups.json")
DEFAULT_GROUP_ID = "default"


def _ensure():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _norm(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def _default_data() -> dict:
    projects = [_norm(p) for p in project_manager.load_recent()]
    return {
        "groups": [
            {
                "id": DEFAULT_GROUP_ID,
                "name": "Projects",
                "collapsed": False,
                "projects": projects,
            }
        ],
        "pinned_projects": [],
    }


def load() -> dict:
    _ensure()
    if not os.path.exists(GROUPS_FILE):
        data = _default_data()
        save(data)
        return data

    try:
        with open(GROUPS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = _default_data()

    if "groups" not in data or not isinstance(data["groups"], list):
        data["groups"] = []
    if "pinned_projects" not in data or not isinstance(data["pinned_projects"], list):
        data["pinned_projects"] = []
    if not data["groups"]:
        data["groups"].append({"id": DEFAULT_GROUP_ID, "name": "Projects", "collapsed": False, "projects": []})

    # Pull in any old recent projects that are not already grouped.
    grouped = set()
    for group in data["groups"]:
        group.setdefault("id", str(uuid.uuid4()))
        group.setdefault("name", "Projects")
        group.setdefault("collapsed", False)
        group.setdefault("projects", [])
        group["projects"] = [_norm(p) for p in group.get("projects", [])]
        grouped.update(group["projects"])

    for path in project_manager.load_recent():
        n = _norm(path)
        if n not in grouped:
            data["groups"][0]["projects"].insert(0, n)
            grouped.add(n)

    data["pinned_projects"] = [_norm(p) for p in data["pinned_projects"]]
    save(data)
    return data


def save(data: dict):
    _ensure()
    with open(GROUPS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def groups() -> list:
    return load().get("groups", [])


def find_group(group_id: str):
    for group in load().get("groups", []):
        if group.get("id") == group_id:
            return group
    return None


def add_group(name: str) -> str:
    data = load()
    gid = str(uuid.uuid4())
    data["groups"].append({"id": gid, "name": name.strip() or "New Group", "collapsed": False, "projects": []})
    save(data)
    return gid


def rename_group(group_id: str, name: str):
    data = load()
    for group in data["groups"]:
        if group.get("id") == group_id:
            group["name"] = name.strip() or group.get("name", "Projects")
            break
    save(data)


def toggle_group(group_id: str):
    data = load()
    for group in data["groups"]:
        if group.get("id") == group_id:
            group["collapsed"] = not bool(group.get("collapsed"))
            break
    save(data)


def remove_group(group_id: str, move_projects_to_default: bool = True):
    data = load()
    if len(data["groups"]) <= 1:
        return

    removed_projects = []
    kept = []
    for group in data["groups"]:
        if group.get("id") == group_id:
            removed_projects = group.get("projects", [])
        else:
            kept.append(group)
    data["groups"] = kept

    if move_projects_to_default and removed_projects:
        data["groups"][0].setdefault("projects", [])
        for path in removed_projects:
            if path not in data["groups"][0]["projects"]:
                data["groups"][0]["projects"].append(path)
    save(data)


def add_project(path: str, group_id: str = None):
    data = load()
    path = _norm(path)
    remove_project(path, save_after=False, data=data)

    target = group_id or data["groups"][0].get("id")
    for group in data["groups"]:
        if group.get("id") == target:
            group.setdefault("projects", []).insert(0, path)
            break
    else:
        data["groups"][0].setdefault("projects", []).insert(0, path)

    project_manager.add_recent(path)
    save(data)


def remove_project(path: str, save_after: bool = True, data: dict = None):
    data = data or load()
    path = _norm(path)
    for group in data.get("groups", []):
        group["projects"] = [p for p in group.get("projects", []) if _norm(p) != path]
    data["pinned_projects"] = [p for p in data.get("pinned_projects", []) if _norm(p) != path]
    project_manager.remove_recent(path)
    if save_after:
        save(data)


def move_project(path: str, direction: int):
    data = load()
    path = _norm(path)
    for group in data.get("groups", []):
        projects = group.get("projects", [])
        if path not in projects:
            continue
        i = projects.index(path)
        j = i + direction
        if 0 <= j < len(projects):
            projects[i], projects[j] = projects[j], projects[i]
            save(data)
        return


def move_project_to_group(path: str, group_id: str):
    data = load()
    path = _norm(path)
    for group in data.get("groups", []):
        group["projects"] = [p for p in group.get("projects", []) if _norm(p) != path]
    for group in data.get("groups", []):
        if group.get("id") == group_id:
            group.setdefault("projects", []).insert(0, path)
            break
    save(data)


def update_project_path(old_path: str, new_path: str):
    data = load()
    old_path = _norm(old_path)
    new_path = _norm(new_path)
    for group in data.get("groups", []):
        group["projects"] = [new_path if _norm(p) == old_path else _norm(p) for p in group.get("projects", [])]
    data["pinned_projects"] = [new_path if _norm(p) == old_path else _norm(p) for p in data.get("pinned_projects", [])]
    project_manager.remove_recent(old_path)
    project_manager.add_recent(new_path)
    save(data)


def pin_project(path: str):
    data = load()
    path = _norm(path)
    if path not in data["pinned_projects"]:
        data["pinned_projects"].append(path)
    save(data)


def unpin_project(path: str):
    data = load()
    path = _norm(path)
    data["pinned_projects"] = [p for p in data["pinned_projects"] if _norm(p) != path]
    save(data)


def is_pinned(path: str) -> bool:
    path = _norm(path)
    return path in load().get("pinned_projects", [])


def pinned_projects() -> list:
    return load().get("pinned_projects", [])