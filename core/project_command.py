"""Per-project command storage for Multi-Commit.

Stored in ~/.config/multi-commit/project_commands.json.
Each project path maps to a list of commands.
"""
import json
import os
import uuid
from datetime import datetime

CONFIG_DIR = os.path.expanduser("~/.config/multi-commit")
COMMANDS_FILE = os.path.join(CONFIG_DIR, "project_commands.json")


def _ensure():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _key(project_path: str) -> str:
    return os.path.abspath(os.path.expanduser(project_path))


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def load_all() -> dict:
    _ensure()
    if not os.path.exists(COMMANDS_FILE):
        return {}
    try:
        with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_all(data: dict):
    _ensure()
    with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def list_commands(project_path: str) -> list:
    data = load_all()
    cmds = data.get(_key(project_path), [])
    return cmds if isinstance(cmds, list) else []


def save_commands(project_path: str, commands: list):
    data = load_all()
    data[_key(project_path)] = commands
    save_all(data)


def new_command(name: str, command: str, use_terminal: bool = False, pinned: bool = False, is_default: bool = False) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": name.strip() or "New Command",
        "command": command.strip(),
        "use_terminal": bool(use_terminal),
        "pinned": bool(pinned),
        "default": bool(is_default),
        "created": _now(),
        "updated": _now(),
    }


def add(project_path: str, name: str, command: str, use_terminal: bool = False, pinned: bool = False, is_default: bool = False):
    cmds = list_commands(project_path)
    if is_default:
        for c in cmds:
            c["default"] = False
    cmd = new_command(name, command, use_terminal, pinned, is_default)
    cmds.append(cmd)
    save_commands(project_path, cmds)
    return cmd


def update(project_path: str, command_id: str, **kwargs):
    cmds = list_commands(project_path)
    if kwargs.get("default"):
        for c in cmds:
            c["default"] = False
    for c in cmds:
        if c.get("id") == command_id:
            c.update(kwargs)
            c["updated"] = _now()
            break
    save_commands(project_path, cmds)


def remove(project_path: str, command_id: str):
    cmds = [c for c in list_commands(project_path) if c.get("id") != command_id]
    save_commands(project_path, cmds)


def move(project_path: str, command_id: str, direction: int):
    cmds = list_commands(project_path)
    for i, c in enumerate(cmds):
        if c.get("id") == command_id:
            j = i + direction
            if 0 <= j < len(cmds):
                cmds[i], cmds[j] = cmds[j], cmds[i]
            break
    save_commands(project_path, cmds)


def set_pinned(project_path: str, command_id: str, pinned: bool):
    update(project_path, command_id, pinned=bool(pinned))


def set_default(project_path: str, command_id: str):
    update(project_path, command_id, default=True)


def get_pinned(project_path: str) -> list:
    return [c for c in list_commands(project_path) if c.get("pinned")]


def get_default(project_path: str):
    for c in list_commands(project_path):
        if c.get("default"):
            return c
    cmds = list_commands(project_path)
    return cmds[0] if cmds else None


def render(command: str, project_path: str, branch: str = "") -> str:
    project = _key(project_path)
    name = os.path.basename(project)
    venv = os.path.join(project, "venv")
    return (command or "").replace("{project}", project).replace("{name}", name).replace("{branch}", branch or "").replace("{venv}", venv)