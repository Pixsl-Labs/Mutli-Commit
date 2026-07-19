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


# ── DevWise checklist completed-status export patch ─────────────────────────
# Export now gives AI useful status context:
# - Stage Status: COMPLETE / IN PROGRESS / NOT STARTED / EMPTY
# - Done: yes/no under each task
#
# Parser also understands Done: yes/no so exported checklists can be re-imported
# without using checkbox syntax.

_dw_status_base_parse_markdown_roadmap = parse_markdown_roadmap


def _dw_status_label(done, total):
    if total <= 0:
        return "EMPTY"
    if done == 0:
        return "NOT STARTED"
    if done >= total:
        return "COMPLETE"
    return "IN PROGRESS"


def _dw_parse_done_value(value):
    value = str(value or "").strip().lower()
    return value in ("yes", "y", "true", "done", "complete", "completed", "1")


def parse_markdown_roadmap(markdown_text):
    import re

    stages = _dw_status_base_parse_markdown_roadmap(markdown_text)

    # Second lightweight pass: apply Done: yes/no lines to the task before them.
    stage_index = -1
    item_index = -1

    for raw in (markdown_text or "").splitlines():
        stripped = raw.strip()

        if not stripped:
            continue

        if re.match(r"^\s*#{1,6}\s*(Branch)\s*:", stripped, flags=re.I):
            continue

        if re.match(r"^\s*#{1,6}\s+", stripped):
            stage_index += 1
            item_index = -1
            continue

        bullet = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$", stripped)
        if bullet and stage_index >= 0:
            item_index += 1
            continue

        done_match = re.match(r"^\s*Done\s*:\s*(.+)$", stripped, flags=re.I)
        if done_match and stage_index >= 0 and item_index >= 0:
            try:
                stages[stage_index]["items"][item_index]["done"] = _dw_parse_done_value(done_match.group(1))
            except Exception:
                pass

    return stages


def export_markdown(project_path, project_name="Project"):
    data = get_project_data(project_path)
    stages = data.get("stages", [])

    done, total = progress_for_project(data)
    overall_status = _dw_status_label(done, total)

    lines = [
        f"# {project_name} — Current Checklist",
        "",
        f"Overall Status: {overall_status}",
        f"Overall Progress: {done} / {total} tasks complete",
        "",
        "Export Notes:",
        "- Done: yes means the task is already completed.",
        "- Done: no means the task is still outstanding.",
        "- COMPLETE stages/issues should usually be kept as completed context, not rewritten as new work.",
        "- IN PROGRESS and NOT STARTED areas are the best places to add/improve next tasks.",
        "",
    ]

    last_branch = object()

    for stage in stages:
        s_done, s_total = progress_for_stage(stage)
        status = _dw_status_label(s_done, s_total)

        branch = stage.get("branch", "")
        issue = stage.get("issue", "")

        if branch and branch != last_branch:
            lines.extend([f"# Branch: {branch}", ""])
            last_branch = branch

        title = issue or stage.get("title", "Untitled Stage")

        if issue:
            lines.append(f"## Issue: {title}")
        else:
            lines.append(f"## Stage: {title}")

        lines.append(f"Stage Status: {status}")
        lines.append(f"Stage Progress: {s_done} / {s_total} tasks complete")

        notes = stage.get("notes", "").strip()
        if notes:
            lines.append(f"Notes: {notes}")

        lines.append("")

        for item in stage.get("items", []):
            task_done = bool(item.get("done"))
            lines.append(f"- {item.get('text', '')}")
            lines.append(f"Done: {'yes' if task_done else 'no'}")

            desc = item.get("description", "").strip()
            if desc:
                lines.append(f"Descript: {desc}")

            lines.append("")

        if s_total > 0 and s_done >= s_total:
            lines.append("Completion Note: This stage/issue is fully complete.")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ── DevWise robust Done/Descript import/export patch ────────────────────────
# Final parser override:
# - Branch / Issue / Stage aware
# - Done: yes/no attaches to the previous task
# - Descript: attaches to the real task, not the Done line
# - Source Checklist / contentReference / oaicite junk is ignored
# - Stage Status / Progress metadata is kept as context, not imported as tasks

def _dw_status_label(done, total):
    if total <= 0:
        return "EMPTY"
    if done == 0:
        return "NOT STARTED"
    if done >= total:
        return "COMPLETE"
    return "IN PROGRESS"


def _dw_parse_done_value(value):
    value = str(value or "").strip().lower()
    return value in ("yes", "y", "true", "done", "complete", "completed", "1", "x")


def _dw_strip_checkbox_and_done(raw):
    import re

    raw = str(raw or "").strip()
    done = False

    m = re.match(r"^\[([ xX])\]\s*(.+)$", raw)
    if m:
        done = m.group(1).lower() == "x"
        raw = m.group(2).strip()

    return raw, done


def _dw_extract_markdown_block(markdown_text):
    import re

    text = markdown_text or ""

    blocks = re.findall(r"```(?:markdown|md|text)?\s*\n([\s\S]*?)```", text, flags=re.I)

    if blocks:
        for block in blocks:
            if "# Branch:" in block or "## Issue:" in block or "Done:" in block or "Descript:" in block:
                return block
        return blocks[0]

    return text


def _dw_is_reference_junk(line):
    lowered = line.lower()
    return (
        "contentreference" in lowered
        or "oaicite" in lowered
        or lowered.startswith("source checklist:")
        or lowered.startswith("source:")
    )


def _dw_is_metadata_line(line):
    lowered = line.strip().lower()

    prefixes = (
        "overall status:",
        "overall progress:",
        "export notes:",
        "current checklist:",
        "format to return:",
        "important output rule:",
        "goal:",
        "status rules:",
        "rules:",
        "completion note:",
        "stage status:",
        "stage progress:",
        "status:",
        "progress:",
    )

    return lowered.startswith(prefixes)


def parse_markdown_roadmap(markdown_text):
    import re

    text = _dw_extract_markdown_block(markdown_text)

    stages = []
    current_branch = ""
    pending_branch_notes = ""
    current_stage = None
    last_item = None
    in_description = False
    in_notes = False
    skipping_export_notes = False

    def append_text(existing, extra):
        extra = str(extra or "").strip()
        if not extra:
            return existing or ""
        existing = str(existing or "").strip()
        return (existing + "\n" + extra).strip() if existing else extra

    def ensure_stage(title="General"):
        nonlocal current_stage
        if current_stage is None:
            current_stage = new_stage(title)
            if current_branch:
                current_stage["branch"] = current_branch
            if pending_branch_notes:
                current_stage["notes"] = pending_branch_notes
            stages.append(current_stage)
        return current_stage

    def start_stage(title, issue=False):
        nonlocal current_stage, last_item, in_description, in_notes, skipping_export_notes

        current_stage = new_stage(title)

        if current_branch:
            current_stage["branch"] = current_branch

        if issue:
            current_stage["issue"] = title

        if pending_branch_notes:
            current_stage["notes"] = pending_branch_notes

        stages.append(current_stage)
        last_item = None
        in_description = False
        in_notes = False
        skipping_export_notes = False

    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            in_description = False
            in_notes = False
            continue

        if stripped.startswith("```"):
            continue

        if _dw_is_reference_junk(stripped):
            continue

        branch_match = re.match(r"^\s*#{1,6}\s*Branch\s*:\s*(.+)$", stripped, flags=re.I)
        if branch_match:
            current_branch = branch_match.group(1).strip()
            pending_branch_notes = ""
            current_stage = None
            last_item = None
            in_description = False
            in_notes = False
            skipping_export_notes = False
            continue

        issue_match = re.match(r"^\s*#{1,6}\s*Issue\s*:\s*(.+)$", stripped, flags=re.I)
        if issue_match:
            start_stage(issue_match.group(1).strip(), issue=True)
            continue

        stage_match = re.match(r"^\s*#{1,6}\s*Stage\s*:\s*(.+)$", stripped, flags=re.I)
        if stage_match:
            start_stage(stage_match.group(1).strip(), issue=False)
            continue

        heading_match = re.match(r"^\s*#{1,6}\s+(.+)$", stripped)
        if heading_match:
            title = heading_match.group(1).strip()

            # Ignore document title headings like "# SentinelIR — Current Checklist"
            if "current checklist" in title.lower() or title.lower().endswith("checklist"):
                continue

            start_stage(title, issue=False)
            continue

        if stripped.lower().startswith("export notes:"):
            skipping_export_notes = True
            continue

        if skipping_export_notes:
            # Skip explanatory export-note bullets until the next heading.
            continue

        notes_match = re.match(r"^\s*Notes\s*:\s*(.*)$", stripped, flags=re.I)
        if notes_match:
            note = notes_match.group(1).strip()

            if current_stage is None:
                pending_branch_notes = append_text(pending_branch_notes, note)
            else:
                current_stage["notes"] = append_text(current_stage.get("notes", ""), note)

            last_item = None
            in_description = False
            in_notes = True
            continue

        done_match = re.match(r"^\s*Done\s*:\s*(.+)$", stripped, flags=re.I)
        if done_match and last_item is not None:
            last_item["done"] = _dw_parse_done_value(done_match.group(1))
            in_description = False
            in_notes = False
            continue

        descript_match = re.match(r"^\s*Descript\s*:\s*(.*)$", stripped, flags=re.I)
        if descript_match and last_item is not None:
            last_item["description"] = append_text(last_item.get("description", ""), descript_match.group(1))
            in_description = True
            in_notes = False
            continue

        if _dw_is_metadata_line(stripped):
            continue

        bullet_match = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$", stripped)
        if bullet_match:
            task_text, done = _dw_strip_checkbox_and_done(bullet_match.group(1))

            # Skip exported instruction bullets before the first real stage/issue.
            if current_stage is None and not current_branch and not stages:
                continue

            if task_text:
                stage = ensure_stage()
                last_item = new_item(task_text, done=done)
                stage.setdefault("items", []).append(last_item)

            in_description = False
            in_notes = False
            continue

        if in_description and last_item is not None:
            last_item["description"] = append_text(last_item.get("description", ""), stripped)
            continue

        if in_notes:
            if current_stage is None:
                pending_branch_notes = append_text(pending_branch_notes, stripped)
            else:
                current_stage["notes"] = append_text(current_stage.get("notes", ""), stripped)
            continue

        # Safe fallback: plain text under a stage becomes notes, not a random task.
        if current_stage is not None:
            current_stage["notes"] = append_text(current_stage.get("notes", ""), stripped)

    return stages


def export_markdown(project_path, project_name="Project"):
    data = get_project_data(project_path)
    stages = data.get("stages", [])

    done, total = progress_for_project(data)
    overall_status = _dw_status_label(done, total)

    lines = [
        f"# {project_name} — Current Checklist",
        "",
        f"Overall Status: {overall_status}",
        f"Overall Progress: {done} / {total} tasks complete",
        "",
        "Export Notes:",
        "- Done: yes means this task is already completed.",
        "- Done: no means this task is still outstanding.",
        "- Completed stages/issues are included as context and should not be recreated as new work.",
        "",
    ]

    last_branch = object()

    for stage in stages:
        s_done, s_total = progress_for_stage(stage)
        status = _dw_status_label(s_done, s_total)

        branch = stage.get("branch", "")
        issue = stage.get("issue", "")
        title = issue or stage.get("title", "Untitled Stage")

        if branch and branch != last_branch:
            lines.extend([f"# Branch: {branch}", ""])
            last_branch = branch

        if issue:
            lines.append(f"## Issue: {title}")
        else:
            lines.append(f"## Stage: {title}")

        lines.append(f"Status: {status}")
        lines.append(f"Progress: {s_done} / {s_total} tasks complete")

        notes = stage.get("notes", "").strip()
        if notes:
            lines.append(f"Notes: {notes}")

        lines.append("")

        for item in stage.get("items", []):
            lines.append(f"- {item.get('text', '')}")
            lines.append(f"Done: {'yes' if item.get('done') else 'no'}")

            desc = item.get("description", "").strip()
            if desc:
                lines.append(f"Descript: {desc}")

            lines.append("")

        if s_total > 0 and s_done >= s_total:
            lines.append("Completion Note: This stage/issue is fully complete.")
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# ── DevWise Git Learning / Done Status checklist patch ──────────────────────
# Supports SentinelIR-style roadmap imports:
# # Branch: feat/name
# Notes: ...
# ## Issue: Title
# Status: COMPLETE
# Progress: 1 / 2 tasks complete
# - Task
# Done: yes
# Descript: details

def _dw_truthy_done(value):
    value = str(value or "").strip().lower()
    return value in {"yes", "y", "true", "done", "complete", "completed", "1", "x"}


def _dw_clean_task_text(text):
    import re
    text = str(text or "").strip()
    text = re.sub(r"^\[[ xX]\]\s*", "", text)
    return text.strip()


def parse_markdown_roadmap(markdown_text):
    import re

    lines = (markdown_text or "").splitlines()
    stages = []
    current_branch = ""
    current_stage = None
    last_item = None
    desc_mode = False
    notes_mode = False

    def start_stage(title, issue=False):
        nonlocal current_stage, last_item, desc_mode, notes_mode

        current_stage = new_stage(title.strip() or "Untitled")
        current_stage["branch"] = current_branch

        if issue:
            current_stage["issue"] = title.strip() or "Untitled"

        stages.append(current_stage)
        last_item = None
        desc_mode = False
        notes_mode = False
        return current_stage

    def ensure_stage():
        nonlocal current_stage
        if current_stage is None:
            return start_stage("General", issue=False)
        return current_stage

    def append_note(stage, value):
        value = str(value or "").strip()
        if not value:
            return
        current = stage.get("notes", "").strip()
        stage["notes"] = (current + "\n" + value).strip() if current else value

    def append_desc(item, value):
        value = str(value or "").strip()
        if not value:
            return
        current = item.get("description", "").strip()
        item["description"] = (current + "\n" + value).strip() if current else value

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            desc_mode = False
            notes_mode = False
            continue

        branch_match = re.match(r"^\s*#{1,6}\s*Branch\s*:\s*(.+)$", stripped, flags=re.I)
        if branch_match:
            current_branch = branch_match.group(1).strip()
            current_stage = None
            last_item = None
            desc_mode = False
            notes_mode = False
            continue

        issue_match = re.match(r"^\s*#{1,6}\s*Issue\s*:\s*(.+)$", stripped, flags=re.I)
        if issue_match:
            start_stage(issue_match.group(1), issue=True)
            continue

        heading_match = re.match(r"^\s*#{1,6}\s+(.+)$", stripped)
        if heading_match:
            title = heading_match.group(1).strip()
            # Backwards compatibility: old headings become stages/issues.
            start_stage(title, issue=False)
            continue

        notes_match = re.match(r"^\s*Notes?\s*:\s*(.*)$", stripped, flags=re.I)
        if notes_match:
            append_note(ensure_stage(), notes_match.group(1))
            last_item = None
            desc_mode = False
            notes_mode = True
            continue

        status_match = re.match(r"^\s*Status\s*:\s*(.+)$", stripped, flags=re.I)
        if status_match:
            ensure_stage()["status"] = status_match.group(1).strip()
            desc_mode = False
            notes_mode = False
            continue

        progress_match = re.match(r"^\s*Progress\s*:\s*(.+)$", stripped, flags=re.I)
        if progress_match:
            # Stored only as source text. Real progress is calculated from tasks.
            ensure_stage()["progress_text"] = progress_match.group(1).strip()
            desc_mode = False
            notes_mode = False
            continue

        done_match = re.match(r"^\s*Done\s*:\s*(.+)$", stripped, flags=re.I)
        if done_match and last_item is not None:
            last_item["done"] = _dw_truthy_done(done_match.group(1))
            desc_mode = False
            notes_mode = False
            continue

        descript_match = re.match(r"^\s*Descript\s*:\s*(.*)$", stripped, flags=re.I)
        if descript_match and last_item is not None:
            append_desc(last_item, descript_match.group(1))
            desc_mode = True
            notes_mode = False
            continue

        bullet_match = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$", stripped)
        if bullet_match:
            task = _dw_clean_task_text(bullet_match.group(1))
            if task:
                last_item = new_item(task)
                ensure_stage().setdefault("items", []).append(last_item)
            desc_mode = False
            notes_mode = False
            continue

        if desc_mode and last_item is not None:
            append_desc(last_item, stripped)
            continue

        if notes_mode and current_stage is not None:
            append_note(current_stage, stripped)
            continue

        # Plain non-metadata text under a stage is treated as notes, not a random task.
        append_note(ensure_stage(), stripped)

    return stages


def export_markdown(project_path, project_name="Project"):
    data = get_project_data(project_path)
    stages = data.get("stages", [])
    lines = [f"# {project_name} — DevWise Checklist", ""]

    last_branch = None

    for stage in stages:
        branch = stage.get("branch", "").strip()
        issue = stage.get("issue", "").strip() or stage.get("title", "Untitled").strip()

        if branch and branch != last_branch:
            lines.extend([f"# Branch: {branch}", ""])
            last_branch = branch

        lines.append(f"## Issue: {issue}")

        status = stage.get("status", "").strip()
        if status:
            lines.append(f"Status: {status}")

        done, total = progress_for_stage(stage)
        lines.append(f"Progress: {done} / {total} tasks complete")

        notes = stage.get("notes", "").strip()
        if notes:
            lines.append(f"Notes: {notes}")

        lines.append("")

        for item in stage.get("items", []):
            lines.append(f"- {item.get('text', '')}")
            lines.append(f"Done: {'yes' if item.get('done') else 'no'}")

            desc = item.get("description", "").strip()
            if desc:
                desc_lines = desc.splitlines()
                lines.append(f"Descript: {desc_lines[0]}")
                for extra in desc_lines[1:]:
                    lines.append(extra)

            lines.append("")

    return "\n".join(lines).rstrip() + "\n"

