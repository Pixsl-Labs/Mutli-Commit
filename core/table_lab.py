"""Table Lab storage for Multi-Commit.

Stores reusable table helper/function snippets in:
~/.config/multi-commit/table_lab.json
"""
import json
import os
import uuid
from datetime import datetime

CONFIG_DIR = os.path.expanduser("~/.config/multi-commit")
TABLE_LAB_FILE = os.path.join(CONFIG_DIR, "table_lab.json")


DEFAULT_FUNCTIONS = '''from colorama import Fore


def format_column(value, width: int, align="<") -> str:
    """
    Formats a value into a fixed-width table column.
    """
    return f"{str(value):{align}{width}}"


def print_table_header(columns: list[tuple]) -> None:
    """
    Prints a formatted table header for CLI output.
    """
    header_row = "   "
    separator_length = 3

    for column in columns:
        if len(column) == 3:
            header, width, align = column
        else:
            header, width = column
            align = "<"

        header_row += format_column(header, width, align)
        separator_length += width

    print(Fore.CYAN + header_row)
    print("   " + Fore.LIGHTBLACK_EX + "-" * separator_length)
'''


def _ensure():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _default_data():
    return {
        "functions": [
            {
                "id": str(uuid.uuid4()),
                "name": "SentinelIR table helpers",
                "code": DEFAULT_FUNCTIONS,
                "created": _now(),
                "updated": _now(),
            }
        ]
    }


def load():
    _ensure()

    if not os.path.exists(TABLE_LAB_FILE):
        data = _default_data()
        save(data)
        return data

    try:
        with open(TABLE_LAB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = _default_data()

    if not isinstance(data, dict):
        data = _default_data()

    data.setdefault("functions", [])
    return data


def save(data):
    _ensure()
    with open(TABLE_LAB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def list_functions():
    return load().get("functions", [])


def add_function(name, code):
    data = load()
    item = {
        "id": str(uuid.uuid4()),
        "name": name.strip() or "Untitled Functions",
        "code": code,
        "created": _now(),
        "updated": _now(),
    }
    data["functions"].append(item)
    save(data)
    return item


def update_function(function_id, name, code):
    data = load()

    for item in data.get("functions", []):
        if item.get("id") == function_id:
            item["name"] = name.strip() or item.get("name", "Untitled Functions")
            item["code"] = code
            item["updated"] = _now()
            save(data)
            return item

    return add_function(name, code)


def remove_function(function_id):
    data = load()
    data["functions"] = [
        item for item in data.get("functions", [])
        if item.get("id") != function_id
    ]
    save(data)
