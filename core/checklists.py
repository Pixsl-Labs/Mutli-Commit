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


# ── DevWise active checklist export helpers ─────────────────────────────────
# Keeps full checklist export available, but lets update prompts focus on
# active/incomplete work instead of repeating completed task detail.

def dw_stage_status(stage):
    done, total = progress_for_stage(stage)

    if total <= 0:
        return "EMPTY"

    if done <= 0:
        return "NOT STARTED"

    if done >= total:
        return "COMPLETE"

    return "IN PROGRESS"


def dw_stage_title(stage):
    return (
        stage.get("issue")
        or stage.get("title")
        or "Untitled issue"
    )


def dw_completed_summary(project_path, project_name="Project"):
    data = get_project_data(project_path)
    stages = data.get("stages", [])

    lines = [f"# {project_name} — Completed Summary", ""]
    count = 0

    last_branch = None

    for stage in stages:
        status = dw_stage_status(stage)

        if status != "COMPLETE":
            continue

        branch = stage.get("branch", "").strip()
        done, total = progress_for_stage(stage)

        if branch and branch != last_branch:
            lines.extend([f"## Branch: {branch}", ""])
            last_branch = branch

        lines.append(f"- {dw_stage_title(stage)} — COMPLETE ({done}/{total})")
        count += 1

    if count == 0:
        lines.append("- No completed issues yet.")

    return "\n".join(lines).rstrip() + "\n"


def dw_active_markdown(project_path, project_name="Project", include_completed_summary=True):
    """
    Export active/incomplete work only.

    Includes:
    - NOT STARTED / IN PROGRESS / EMPTY issues
    - incomplete tasks
    - optional compact completed summary

    Excludes by default:
    - full completed task lists
    - completed descriptions
    """
    data = get_project_data(project_path)
    stages = data.get("stages", [])

    lines = [f"# {project_name} — Active DevWise Checklist", ""]
    last_branch = None
    active_count = 0

    for stage in stages:
        status = dw_stage_status(stage)

        if status == "COMPLETE":
            continue

        branch = stage.get("branch", "").strip()
        issue = dw_stage_title(stage)
        done, total = progress_for_stage(stage)

        if branch and branch != last_branch:
            lines.extend([f"# Branch: {branch}", ""])
            last_branch = branch

        lines.append(f"## Issue: {issue}")
        lines.append(f"Stage Status: {status}")
        lines.append(f"Stage Progress: {done} / {total} tasks complete")

        notes = stage.get("notes", "").strip()
        if notes:
            lines.append(f"Notes: {notes}")

        lines.append("")

        items = stage.get("items", [])

        if not items:
            lines.append("- Define next task")
            lines.append("Done: no")
            lines.append("Descript: Add the first useful task for this issue.")
            lines.append("")
        else:
            any_incomplete = False

            for item in items:
                if item.get("done"):
                    continue

                any_incomplete = True
                lines.append(f"- {item.get('text', '')}")
                lines.append("Done: no")

                desc = item.get("description", "").strip()
                if desc:
                    desc_lines = desc.splitlines()
                    lines.append(f"Descript: {desc_lines[0]}")
                    for extra in desc_lines[1:]:
                        lines.append(extra)
                else:
                    lines.append("Descript: Add useful implementation detail.")

                lines.append("")

            if not any_incomplete and status != "COMPLETE":
                lines.append("- Review issue status")
                lines.append("Done: no")
                lines.append("Descript: This issue is not marked complete but has no outstanding tasks.")
                lines.append("")

        active_count += 1

    if active_count == 0:
        lines.append("## Issue: Next work")
        lines.append("Stage Status: NOT STARTED")
        lines.append("Stage Progress: 0 / 1 tasks complete")
        lines.append("")
        lines.append("- Decide next improvement")
        lines.append("Done: no")
        lines.append("Descript: Add the next useful DevWise improvement.")
        lines.append("")

    if include_completed_summary:
        summary = dw_completed_summary(project_path, project_name)
        lines.extend([
            "",
            "---",
            "",
            summary.rstrip(),
            "",
            "Note: completed work is summarised only. Do not expand completed work unless I explicitly ask.",
        ])

    return "\n".join(lines).rstrip() + "\n"


def dw_update_prompt_active(project_path, project_name="Project"):
    active = dw_active_markdown(
        project_path,
        project_name,
        include_completed_summary=True,
    )

    return (
        "Update this DevWise checklist.\n\n"
        "IMPORTANT OUTPUT RULE:\n"
        "Return only one clean markdown code block containing the updated checklist.\n"
        "Do not include explanations, citations, source labels, contentReference tags, oaicite tags, or tables.\n\n"
        "Main goal:\n"
        "- Focus on active, incomplete, not-started, or in-progress work.\n"
        "- Keep useful existing branches, issues, tasks, notes and descriptions.\n"
        "- Add missing branches/issues/tasks where useful.\n"
        "- Improve wording where helpful.\n"
        "- Do not delete useful existing work unless it is clearly duplicated or I explicitly ask.\n\n"
        "Completed-work rule:\n"
        "- Completed work is included only as a compact summary.\n"
        "- Do not recreate full completed task lists.\n"
        "- Do not turn completed work back into outstanding work unless I explicitly ask.\n\n"
        "Required format:\n"
        "# Branch: feat/example-branch\n"
        "Notes: Optional branch/workstream context.\n\n"
        "## Issue: Short issue title\n"
        "Stage Status: IN PROGRESS\n"
        "Stage Progress: 1 / 2 tasks complete\n\n"
        "- Task name\n"
        "Done: no\n"
        "Descript: Useful detail for the task.\n\n"
        "Rules:\n"
        "- Use Branch → Issue → Task → Done → Descript format.\n"
        "- Use Done: yes/no under each task.\n"
        "- Do not use checkbox syntax like [ ] or [x].\n"
        "- Do not use tables.\n\n"
        "Current active checklist context:\n\n"
        "```markdown\n"
        f"{active.rstrip()}\n"
        "\n```\n"
    )


# ── DevWise branch container parser/export patch ────────────────────────────
def _dw_norm_bool(value):
    value = str(value or "").strip().lower()
    return value in {"yes", "y", "true", "done", "complete", "completed", "1", "x"}


def _dw_calc_status(done, total):
    if total <= 0:
        return "EMPTY"
    if done <= 0:
        return "NOT STARTED"
    if done >= total:
        return "COMPLETE"
    return "IN PROGRESS"


def _dw_clean_heading_title(title):
    import re
    title = str(title or "").strip()
    title = re.sub(r"\s*\(\d+\s*/\s*\d+\)\s*$", "", title).strip()
    return title


def _dw_clean_task_text(raw):
    import re
    text = str(raw or "").strip()
    text = re.sub(r"^\[[ xX]\]\s*", "", text)
    return text.strip()


def parse_markdown_roadmap(markdown_text):
    """
    Final DevWise roadmap parser.

    Key rule:
    # Branch: x is a container only. It never creates a blank stage by itself.
    Stages/issues only begin at ## Issue: or ## Stage: headings.
    """
    import re

    stages = []
    current_branch = ""
    current_branch_notes = ""
    current_stage = None
    last_item = None
    desc_mode = False
    notes_mode = False
    ignore_rest = False

    def is_junk_line(line):
        lowered = line.strip().lower()
        return (
            not lowered
            or lowered.startswith("contentreference")
            or lowered.startswith("source:")
            or lowered.startswith("oaicite")
            or lowered.startswith("")
            or lowered in {"```", "```markdown", "```text"}
        )

    def append_text(existing, value):
        value = str(value or "").strip()
        if not value:
            return existing or ""
        existing = str(existing or "").strip()
        return (existing + "\n" + value).strip() if existing else value

    def start_stage(title, kind="Issue"):
        nonlocal current_stage, last_item, desc_mode, notes_mode

        clean_title = _dw_clean_heading_title(title) or "Untitled"
        current_stage = new_stage(clean_title)
        current_stage["branch"] = current_branch
        current_stage["issue"] = clean_title if kind.lower() == "issue" else ""
        current_stage["kind"] = kind

        if current_branch_notes:
            current_stage["branch_notes"] = current_branch_notes

        stages.append(current_stage)
        last_item = None
        desc_mode = False
        notes_mode = False
        return current_stage

    for raw in (markdown_text or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if is_junk_line(stripped):
            desc_mode = False
            notes_mode = False
            continue

        if stripped == "---":
            ignore_rest = True
            continue

        if "completed summary" in stripped.lower():
            ignore_rest = True
            continue

        branch_match = re.match(r"^\s*#{1,6}\s*Branch\s*:\s*(.+)$", stripped, flags=re.I)
        if branch_match:
            ignore_rest = False
            current_branch = branch_match.group(1).strip()
            current_branch_notes = ""
            current_stage = None
            last_item = None
            desc_mode = False
            notes_mode = False
            continue

        if ignore_rest:
            continue

        # Ignore document title headings, not real work stages.
        if re.match(r"^\s*#\s+.+?(Checklist|Active DevWise Checklist|Current Checklist)\s*$", stripped, flags=re.I):
            current_stage = None
            last_item = None
            continue

        issue_match = re.match(r"^\s*#{1,6}\s*Issue\s*:\s*(.+)$", stripped, flags=re.I)
        if issue_match:
            start_stage(issue_match.group(1), "Issue")
            continue

        stage_match = re.match(r"^\s*#{1,6}\s*Stage\s*:\s*(.+)$", stripped, flags=re.I)
        if stage_match:
            start_stage(stage_match.group(1), "Stage")
            continue

        # Backwards compatibility: non-branch headings below h2 become stages.
        generic_heading = re.match(r"^\s*#{2,6}\s+(.+)$", stripped)
        if generic_heading:
            title = generic_heading.group(1).strip()
            if title and not title.lower().startswith(("export notes", "rules", "current active checklist context")):
                start_stage(title, "Stage")
            continue

        notes_match = re.match(r"^\s*Notes?\s*:\s*(.*)$", stripped, flags=re.I)
        if notes_match:
            value = notes_match.group(1).strip()

            if current_stage is None:
                current_branch_notes = append_text(current_branch_notes, value)
            else:
                current_stage["notes"] = append_text(current_stage.get("notes", ""), value)

            last_item = None
            desc_mode = False
            notes_mode = True
            continue

        status_match = re.match(r"^\s*(?:Stage\s+)?Status\s*:\s*(.+)$", stripped, flags=re.I)
        if status_match and current_stage is not None:
            current_stage["status"] = status_match.group(1).strip()
            desc_mode = False
            notes_mode = False
            continue

        progress_match = re.match(r"^\s*(?:Stage\s+)?Progress\s*:\s*(.+)$", stripped, flags=re.I)
        if progress_match and current_stage is not None:
            current_stage["progress_text"] = progress_match.group(1).strip()
            desc_mode = False
            notes_mode = False
            continue

        done_match = re.match(r"^\s*Done\s*:\s*(.+)$", stripped, flags=re.I)
        if done_match and last_item is not None:
            last_item["done"] = _dw_norm_bool(done_match.group(1))
            desc_mode = False
            notes_mode = False
            continue

        descript_match = re.match(r"^\s*Descript\s*:\s*(.*)$", stripped, flags=re.I)
        if descript_match and last_item is not None:
            last_item["description"] = append_text(last_item.get("description", ""), descript_match.group(1))
            desc_mode = True
            notes_mode = False
            continue

        bullet_match = re.match(r"^\s*(?:[-*+]|\d+[.)])\s+(.+)$", stripped)
        if bullet_match:
            # Important: do not create a fake stage from bullets under branch notes or completed summary.
            if current_stage is None:
                current_branch_notes = append_text(current_branch_notes, _dw_clean_task_text(bullet_match.group(1)))
                continue

            task = _dw_clean_task_text(bullet_match.group(1))
            if task:
                last_item = new_item(task)
                current_stage.setdefault("items", []).append(last_item)

            desc_mode = False
            notes_mode = False
            continue

        if desc_mode and last_item is not None:
            last_item["description"] = append_text(last_item.get("description", ""), stripped)
            continue

        if notes_mode:
            if current_stage is None:
                current_branch_notes = append_text(current_branch_notes, stripped)
            else:
                current_stage["notes"] = append_text(current_stage.get("notes", ""), stripped)
            continue

        # Plain text under a branch but before an issue is branch notes, not an empty stage.
        if current_stage is None:
            current_branch_notes = append_text(current_branch_notes, stripped)
        else:
            current_stage["notes"] = append_text(current_stage.get("notes", ""), stripped)

    # Remove truly empty accidental stages if any older import created them.
    cleaned = []
    for stage in stages:
        title = str(stage.get("title", "")).strip().lower()
        has_items = bool(stage.get("items"))
        has_notes = bool(str(stage.get("notes", "")).strip())
        has_issue = bool(str(stage.get("issue", "")).strip())

        if title in {"general", "untitled", "untitled stage"} and not has_items and not has_notes and not has_issue:
            continue

        cleaned.append(stage)

    return cleaned


def dw_branch_display_name(stage):
    branch = str(stage.get("branch", "") or "").strip()
    return branch if branch else "No branch"


def dw_stage_display_title(stage):
    return (
        str(stage.get("issue", "") or "").strip()
        or str(stage.get("title", "") or "").strip()
        or "Untitled"
    )


def export_markdown(project_path, project_name="Project"):
    data = get_project_data(project_path)
    stages = data.get("stages", [])
    done, total = progress_for_project(data)

    lines = [
        f"# {project_name} — Current Checklist",
        "",
        f"Overall Status: {_dw_calc_status(done, total)}",
        f"Overall Progress: {done} / {total} tasks complete",
        "",
    ]

    last_branch = object()

    for stage in stages:
        branch = str(stage.get("branch", "") or "").strip()
        s_done, s_total = progress_for_stage(stage)
        status = _dw_calc_status(s_done, s_total)

        if branch and branch != last_branch:
            lines.append(f"# Branch: {branch}")
            branch_notes = str(stage.get("branch_notes", "") or "").strip()
            if branch_notes:
                lines.append(f"Notes: {branch_notes}")
            lines.append("")
            last_branch = branch

        issue = str(stage.get("issue", "") or "").strip()
        title = dw_stage_display_title(stage)

        if issue:
            lines.append(f"## Issue: {title}")
        else:
            lines.append(f"## Stage: {title}")

        lines.append(f"Status: {status}")
        lines.append(f"Progress: {s_done} / {s_total} tasks complete")

        notes = str(stage.get("notes", "") or "").strip()
        if notes:
            lines.append(f"Notes: {notes}")

        lines.append("")

        for item in stage.get("items", []):
            lines.append(f"- {item.get('text', '')}")
            lines.append(f"Done: {'yes' if item.get('done') else 'no'}")

            desc = str(item.get("description", "") or "").strip()
            if desc:
                desc_lines = desc.splitlines()
                lines.append(f"Descript: {desc_lines[0]}")
                for extra in desc_lines[1:]:
                    lines.append(extra)

            lines.append("")

    return "\n".join(lines).rstrip() + "\n"



# ── DevWise branch labels parser/export patch ───────────────────────────────
# Adds support for:
# # Branch: feat/example
# Labels: enhancement, frontend, priority-medium
#
# The existing parser still handles branches/issues/tasks.
# This wrapper extracts branch-level labels and applies them to every stage
# inside that branch.

def _dw_labels_clean(value):
    labels = []

    for part in str(value or "").replace(";", ",").split(","):
        label = part.strip().strip("`").strip()

        if not label:
            continue

        if label not in labels:
            labels.append(label)

    return labels


def _dw_labels_extract_branch_labels(markdown_text):
    import re

    labels_by_branch = {}
    current_branch = ""

    for raw in (markdown_text or "").splitlines():
        line = raw.strip()

        branch_match = re.match(r"^\s*#{1,6}\s*Branch\s*:\s*(.+)$", line, flags=re.I)
        if branch_match:
            current_branch = branch_match.group(1).strip()
            labels_by_branch.setdefault(current_branch, [])
            continue

        labels_match = re.match(r"^\s*Labels?\s*:\s*(.+)$", line, flags=re.I)
        if labels_match and current_branch:
            labels_by_branch[current_branch] = _dw_labels_clean(labels_match.group(1))

    return labels_by_branch


if not globals().get("_dw_branch_labels_parser_patch_applied", False):
    _dw_branch_labels_base_parse_markdown_roadmap = parse_markdown_roadmap
    _dw_branch_labels_base_export_markdown = export_markdown

    def parse_markdown_roadmap(markdown_text):
        stages = _dw_branch_labels_base_parse_markdown_roadmap(markdown_text)
        labels_by_branch = _dw_labels_extract_branch_labels(markdown_text)

        for stage in stages:
            branch = str(stage.get("branch", "") or "").strip()

            if branch and branch in labels_by_branch:
                stage["labels"] = labels_by_branch.get(branch, [])

        return stages

    def export_markdown(project_path, project_name="Project"):
        text = _dw_branch_labels_base_export_markdown(project_path, project_name)

        data = get_project_data(project_path)
        branch_labels = {}

        for stage in data.get("stages", []):
            branch = str(stage.get("branch", "") or "").strip()
            labels = stage.get("labels", [])

            if branch and labels:
                branch_labels[branch] = _dw_labels_clean(", ".join(labels))

        if not branch_labels:
            return text

        lines = []
        current_branch = ""

        for line in text.splitlines():
            lines.append(line)

            import re
            branch_match = re.match(r"^\s*#\s*Branch\s*:\s*(.+)$", line.strip(), flags=re.I)

            if branch_match:
                current_branch = branch_match.group(1).strip()
                labels = branch_labels.get(current_branch, [])

                if labels:
                    lines.append("Labels: " + ", ".join(labels))

        return "\n".join(lines).rstrip() + "\n"

    _dw_branch_labels_parser_patch_applied = True

