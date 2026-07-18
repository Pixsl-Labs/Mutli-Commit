"""Project templates for DevWise."""
import os
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from core import checklists, project_commands, activity


TEMPLATES = {
    "python_cli": {
        "name": "Python CLI Project",
        "commands": [
            ("Run app", "python3 main.py", True, True),
            ("Compile check", "python3 -m py_compile main.py core/*.py ui/*.py", False, True),
            ("Git status", "git status --short", False, False),
        ],
        "roadmap": [
            ("Project setup", [
                ("Confirm app launches", "Run the app from terminal and verify there are no startup errors."),
                ("Add compile check", "Make sure Python files compile cleanly before committing."),
                ("Document useful commands", "Save repeated terminal commands as project commands."),
            ]),
            ("Testing", [
                ("Add basic tests", "Create small tests for core logic before expanding features."),
                ("Run regression check", "Check existing functionality after each patch."),
            ]),
        ],
    },
    "gtk_desktop": {
        "name": "GTK Desktop App",
        "commands": [
            ("Run app", "python3 main.py", True, True),
            ("Compile UI", "python3 -m py_compile main.py core/*.py ui/*.py", False, True),
            ("Open logs", "xdg-open ~/.config", True, False),
        ],
        "roadmap": [
            ("UI foundation", [
                ("Check main window layout", "Confirm sidebar, middle panel and right panel are usable/resizable."),
                ("Add tooltips", "Common buttons should explain what they do."),
                ("Avoid blocking UI", "Long-running checks should not freeze GTK."),
            ]),
            ("Release polish", [
                ("Update README", "Document install, launch and important features."),
                ("Test desktop launcher", "Run install.sh and confirm the app appears in the menu."),
            ]),
        ],
    },
    "cyber_dissertation": {
        "name": "Cyber Dissertation Tool",
        "commands": [
            ("Run app", "python3 main.py", True, True),
            ("Run tests", "pytest", True, True),
            ("Generate sample logs", "python3 generator.py", True, False),
            ("Git status", "git status --short", False, False),
        ],
        "roadmap": [
            ("Investigation workflow", [
                ("Define input sources", "List logs/events/files the tool can ingest."),
                ("Build repeatable scenarios", "Create generator scenarios for brute force, suspicious success and normal activity."),
                ("Document outputs", "Clarify reports, alerts, tables and investigation notes produced by the tool."),
            ]),
            ("Evaluation", [
                ("Plan usability testing", "Prepare tasks for students/users to try the tool."),
                ("Add unit tests", "Test parsing, detections, suppression and report generation."),
            ]),
        ],
    },
}


def _add_command_safe(project_path, name, command, use_terminal=False, pinned=False):
    try:
        return project_commands.add(project_path, name, command, use_terminal, pinned, is_default=False)
    except TypeError:
        try:
            return project_commands.add(project_path, name, command, use_terminal, pinned, False)
        except TypeError:
            return project_commands.add(project_path, name, command)


class ProjectTemplatesWindow(Gtk.Window):
    def __init__(self, parent=None, project_path=None):
        super().__init__(title="🧩 DevWise Project Templates")
        self.parent_window = parent
        self.project_path = os.path.abspath(os.path.expanduser(project_path)) if project_path else None
        self.set_default_size(620, 420)
        self.set_position(Gtk.WindowPosition.CENTER)
        self._build()
        self.show_all()

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_border_width(12)
        self.add(root)

        title = Gtk.Label()
        title.set_markup("<b>🧩 Project Templates</b>")
        title.set_halign(Gtk.Align.START)
        root.pack_start(title, False, False, 0)

        self.path_lbl = Gtk.Label(label=self.project_path or "No project selected")
        self.path_lbl.set_halign(Gtk.Align.START)
        root.pack_start(self.path_lbl, False, False, 0)

        self.combo = Gtk.ComboBoxText()
        for key, item in TEMPLATES.items():
            self.combo.append(key, item["name"])
        self.combo.set_active(0)
        root.pack_start(self.combo, False, False, 0)

        hint = Gtk.Label(label="Applies starter commands and a starter checklist. It appends, it does not delete existing work.")
        hint.set_halign(Gtk.Align.START)
        hint.set_line_wrap(True)
        root.pack_start(hint, False, False, 0)

        self.replace_check = Gtk.CheckButton(label="Replace existing checklist stages")
        self.replace_check.set_active(False)
        root.pack_start(self.replace_check, False, False, 0)

        apply_btn = Gtk.Button(label="Apply Template")
        apply_btn.connect("clicked", self.apply_template)
        root.pack_start(apply_btn, False, False, 0)

        self.result_lbl = Gtk.Label(label="")
        self.result_lbl.set_halign(Gtk.Align.START)
        self.result_lbl.set_line_wrap(True)
        root.pack_start(self.result_lbl, False, False, 0)

    def apply_template(self, _=None):
        if not self.project_path:
            self.result_lbl.set_text("Select a project first.")
            return

        key = self.combo.get_active_id()
        template = TEMPLATES.get(key)

        if not template:
            self.result_lbl.set_text("No template selected.")
            return

        for name, command, use_terminal, pinned in template.get("commands", []):
            _add_command_safe(self.project_path, name, command, use_terminal, pinned)

        project_data = checklists.get_project_data(self.project_path)
        imported = []

        for stage_title, tasks in template.get("roadmap", []):
            stage = checklists.new_stage(stage_title)
            stage["branch"] = ""
            stage["issue"] = stage_title
            for task_text, desc in tasks:
                stage.setdefault("items", []).append(checklists.new_item(task_text, description=desc))
            imported.append(stage)

        checklists.merge_imported_stages(
            project_data,
            imported,
            replace=self.replace_check.get_active()
        )
        checklists.save_project_data(self.project_path, project_data)

        try:
            activity.log_event(self.project_path, "template_applied", f"Applied template: {template['name']}")
        except Exception:
            pass

        self.result_lbl.set_text(f"Applied: {template['name']}")
