"""User settings, persisted to ~/.config/multi-commit/settings.json"""
import json
import os

CONFIG_DIR = os.path.expanduser("~/.config/multi-commit")
SETTINGS_FILE = os.path.join(CONFIG_DIR, "settings.json")

DEFAULTS = {
    "auto_git_add": False,
    "auto_git_push": False,
    "default_add_target": ".",
    "vscode_cmd": "code",
    "terminal_cmd": "kitty",
    "default_remote": "origin",
    "code_review_output_dir": "~/Projects/Code Reviews",
    "code_review_folders": ["~/Projects/Code Reviews"],
    "custom_commit_templates": [],
    "dashboard_refresh_interval": 60,
}

def _ensure_config():
    os.makedirs(CONFIG_DIR, exist_ok=True)

def load():
    _ensure_config()
    if not os.path.exists(SETTINGS_FILE):
        return DEFAULTS.copy()
    try:
        with open(SETTINGS_FILE) as f:
            data = json.load(f)
        # Merge with defaults so new keys always exist
        merged = DEFAULTS.copy()
        merged.update(data)
        return merged
    except Exception:
        return DEFAULTS.copy()

def save(settings: dict):
    _ensure_config()
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)

def get(key):
    return load().get(key, DEFAULTS.get(key))

def set_value(key, value):
    s = load()
    s[key] = value
    save(s)