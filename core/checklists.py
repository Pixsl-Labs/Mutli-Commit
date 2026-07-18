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


# ── DevWise Branch/Issue checklist parser patch ─────────────────────────────
# Adds backwards-compatible support for:
# # Branch: feat/example
# ## Issue: Build thing
# - Task
# Descript: details

_dw_base_parse_markdown_roadmap = parse_markdown_roadmap
_dw_base_export_markdown = export_markdown


def _dw_strip_checkbox(text):
    import re
    return re.sub(r"^\s*\[[ xX]\]\s*", "", str(text or "")).strip()


def parse_markdown_roadmap(markdown_text):
    import re

    text = markdown_text or ""

    if not re.search(r"^\s*#{1,6}\s*(Branch|Issue)\s*:", text, flags=re.I | re.M):
        return _dw_base_parse_markdown_roadmap(text)

    stages = []
    current_branch = ""
    current_stage = None
    last_item = None
    desc_mode = False

    def ensure_stage(title="General"):
        nonlocal current_stage
        if current_stage is None:
            current_stage = new_stage(title)
            current_stage["branch"] = current_branch
            stages.append(current_stage)
        return current_stage

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            desc_mode = False
            continue

        branch_match = re.match(r"^\s*#{1,6}\s*Branch\s*:\s*(.+)$", stripped, flags=re.I)
        if branch_match:
            current_branch = branch_match.group(1).strip()
            current_stage = None
            last_item = None
            desc_mode = False
            continue

        issue_match = re.match(r"^\s*#{1,6}\s*Issue\s*:\s*(.+)$", stripped, flags=re.I)
        if issue_match:
            issue_title = issue_match.group(1).strip()
            current_stage = new_stage(issue_title)
            current_stage["branch"] = current_branch
            current_stage["issue"] = issue_title
            stages.append(current_stage)
            last_item = None
            desc_mode = False
            continue

        heading = re.match(r"^\s*#{1,6}\s+(.+)$", stripped)
        if heading:
            title = heading.group(1).strip()
            current_stage = new_stage(title)
            current_stage["branch"] = current_branch
            stages.append(current_stage)
            last_item = None
            desc_mode = False
            continue

        notes_match = re.match(r"^\s*Notes\s*:\s*(.*)$", stripped, flags=re.I)
        if notes_match:
            stage = ensure_stage()
            stage["notes"] = notes_match.group(1).strip()
            last_item = None
            desc_mode = False
            continue

        descript_match = re.match(r"^\s*Descript\s*:\s*(.*)$", stripped, flags=re.I)
        if descript_match and last_item is not None:
            last_item["description"] = descript_match.group(1).strip()
            desc_mode = True
            continue

        bullet = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$", stripped)
        if bullet:
            stage = ensure_stage()
            task_text = _dw_strip_checkbox(bullet.group(1))
            if task_text:
                last_item = new_item(task_text)
                stage.setdefault("items", []).append(last_item)
            desc_mode = False
            continue

        if desc_mode and last_item is not None:
            current = last_item.get("description", "").strip()
            last_item["description"] = (current + "\n" + stripped).strip() if current else stripped
            continue

        # Fallback: useful plain lines become tasks inside current issue/stage.
        if current_stage is not None:
            last_item = new_item(_dw_strip_checkbox(stripped))
            current_stage.setdefault("items", []).append(last_item)
            desc_mode = False

    return stages


def export_markdown(project_path, project_name="Project"):
    data = get_project_data(project_path)
    stages = data.get("stages", [])

    lines = [f"# {project_name} Checklist", ""]

    last_branch = object()

    for stage in stages:
        branch = stage.get("branch", "")
        issue = stage.get("issue", "")

        if branch and branch != last_branch:
            lines.extend([f"# Branch: {branch}", ""])
            last_branch = branch

        if issue:
            lines.append(f"## Issue: {issue}")
        else:
            lines.append(f"# {stage.get('title', 'Untitled Stage')}")

        notes = stage.get("notes", "").strip()
        if notes:
            lines.append(f"Notes: {notes}")

        lines.append("")

        for item in stage.get("items", []):
            box = "x" if item.get("done") else " "
            lines.append(f"- [{box}] {item.get('text', '')}")
            desc = item.get("description", "").strip()
            if desc:
                lines.append(f"Descript: {desc}")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"

