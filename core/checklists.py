"""Per-project checklist/roadmap storage — ~/.config/multi-commit/checklists.json"""
import json
import os
import re
from datetime import datetime

CONFIG_DIR = os.path.expanduser("~/.config/multi-commit")
CHECKLIST_FILE = os.path.join(CONFIG_DIR, "checklists.json")


def _ensure():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_all() -> dict:
    """Load the full checklist store: {project_path: {stages: [...], updated: ...}}"""
    _ensure()
    if not os.path.exists(CHECKLIST_FILE):
        return {}
    try:
        with open(CHECKLIST_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def save_all(data: dict):
    _ensure()
    with open(CHECKLIST_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_project_data(project_path: str) -> dict:
    """Return the checklist data for a project, or a fresh empty structure."""
    data = load_all()
    key = os.path.abspath(os.path.expanduser(project_path))
    return data.get(key, {"stages": [], "created": None, "updated": None})


def save_project_data(project_path: str, project_data: dict):
    data = load_all()
    key = os.path.abspath(os.path.expanduser(project_path))

    now = datetime.now().isoformat(timespec="seconds")
    if not project_data.get("created"):
        project_data["created"] = now
    project_data["updated"] = now

    data[key] = project_data
    save_all(data)


# ── Stage / item helpers ──────────────────────────────────────────────────

def new_stage(title: str, notes: str = "") -> dict:
    return {"title": title, "notes": notes, "items": []}


def new_item(text: str, done: bool = False, description: str = "") -> dict:
    return {"text": text, "done": done, "description": description}


def progress_for_stage(stage: dict) -> tuple:
    items = stage.get("items", [])
    total = len(items)
    done = sum(1 for i in items if i.get("done"))
    return done, total


def progress_for_project(project_data: dict) -> tuple:
    total = 0
    done = 0
    for stage in project_data.get("stages", []):
        d, t = progress_for_stage(stage)
        total += t
        done += d
    return done, total


# ── Markdown roadmap parser ─────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_BULLET_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_CHECKBOX_RE = re.compile(r"^\[[ xX]\]\s+(.*)$")
_DESCRIPT_RE = re.compile(r"^\s*Descript:\s*(.*)$", re.IGNORECASE)
_NOTES_RE = re.compile(r"^\s*Notes?:\s*(.*)$", re.IGNORECASE)


def parse_markdown_roadmap(text: str) -> list:
    """
    Parse a markdown roadmap into a list of stage dicts.

    Rules:
    - Lines starting with #, ##, ### etc. start a new stage.
    - Notes: lines become stage notes.
    - Numbered and bullet items become checklist items.
    - Descript: lines directly after an item become that item's task description.
    - Extra lines after Notes: continue notes until the next item/heading.
    - Extra lines after Descript: continue description until the next item/heading.
    - Checkbox syntax [ ]/[x] is tolerated but stripped.
    """
    stages = []
    current = None
    last_item = None
    in_description = False
    in_notes = False

    def ensure_current():
        nonlocal current
        if current is None:
            current = new_stage("General")
            stages.append(current)
        return current

    def clean_item_text(raw: str) -> str:
        raw = raw.strip()
        checkbox = _CHECKBOX_RE.match(raw)
        if checkbox:
            return checkbox.group(1).strip()
        return raw

    def append_stage_note(stage: dict, note: str):
        note = note.strip()
        if not note:
            return
        if stage.get("notes"):
            stage["notes"] += "\n" + note
        else:
            stage["notes"] = note

    def append_item_description(item: dict, desc: str):
        desc = desc.strip()
        if not desc:
            return
        existing = item.get("description", "").strip()
        item["description"] = (existing + "\n" + desc).strip() if existing else desc

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if not line.strip():
            in_description = False
            in_notes = False
            continue

        heading_match = _HEADING_RE.match(line)
        if heading_match:
            title = heading_match.group(2).strip()
            if title:
                current = new_stage(title)
                stages.append(current)
                last_item = None
                in_description = False
                in_notes = False
            continue

        notes_match = _NOTES_RE.match(line)
        if notes_match:
            stage = ensure_current()
            append_stage_note(stage, notes_match.group(1))
            last_item = None
            in_description = False
            in_notes = True
            continue

        descript_match = _DESCRIPT_RE.match(line)
        if descript_match and last_item is not None:
            append_item_description(last_item, descript_match.group(1))
            in_description = True
            in_notes = False
            continue

        numbered_match = _NUMBERED_RE.match(line)
        bullet_match = _BULLET_RE.match(line)

        if numbered_match or bullet_match:
            item_text = clean_item_text((numbered_match or bullet_match).group(1))
            if item_text:
                last_item = new_item(item_text)
                ensure_current()["items"].append(last_item)
                in_description = False
                in_notes = False
            continue

        if in_description and last_item is not None:
            append_item_description(last_item, line)
            continue

        if in_notes:
            append_stage_note(ensure_current(), line)
            continue

        append_stage_note(ensure_current(), line)

    return stages

def merge_imported_stages(project_data: dict, imported_stages: list, replace: bool = False) -> dict:
    """
    Merge freshly-imported stages into existing project data.

    If replace=True, the existing stages are discarded entirely.
    Otherwise imported stages are appended after existing ones.
    """
    if replace or "stages" not in project_data:
        project_data["stages"] = imported_stages
    else:
        project_data["stages"].extend(imported_stages)
    return project_data

# ── Export / Delete ─────────────────────────────────────────────────────────

def export_markdown(project_path: str, project_name: str = None) -> str:
    """Build an AI-friendly markdown export of a project's checklist."""
    project_data = get_project_data(project_path)
    name = project_name or os.path.basename(os.path.abspath(os.path.expanduser(project_path)))
    done, total = progress_for_project(project_data)

    lines = [
        f"# {name} — Checklist",
        "",
        f"**Progress:** {done} / {total} items complete",
        "",
    ]

    for stage in project_data.get("stages", []):
        s_done, s_total = progress_for_stage(stage)
        lines.append(f"## {stage.get('title', 'Untitled')} ({s_done}/{s_total})")
        lines.append("")

        for item in stage.get("items", []):
            box = "[x]" if item.get("done") else "[ ]"
            lines.append(f"- {box} {item.get('text', '')}")
            desc = item.get("description", "").strip()
            if desc:
                desc_lines = desc.splitlines()
                lines.append(f"  Descript: {desc_lines[0]}")
                for extra in desc_lines[1:]:
                    lines.append(f"  {extra}")

        notes = stage.get("notes", "").strip()
        if notes:
            lines.append("")
            lines.append("**Notes:**")
            lines.append("")
            lines.append(notes)

        lines.append("")

    return "\n".join(lines)


def delete_project_data(project_path: str):
    """Delete checklist data for a single project only."""
    data = load_all()
    key = os.path.abspath(os.path.expanduser(project_path))
    if key in data:
        del data[key]
        save_all(data)