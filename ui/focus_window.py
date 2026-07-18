"""Focus Mode window for DevWise."""
import os
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango

from core import git_ops, checklists, issues, project_commands


class FocusWindow(Gtk.Window):
    def __init__(self, parent=None, project_path=None):
        super().__init__(title="🎯 DevWise Focus Mode")
        self.parent_window = parent
        self.project_path = os.path.abspath(os.path.expanduser(project_path)) if project_path else None
        self.set_default_size(720, 520)
        self.set_position(Gtk.WindowPosition.CENTER)
        self._build()
        self.refresh()
        self.show_all()

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_border_width(12)
        self.add(root)

        self.title_lbl = Gtk.Label()
        self.title_lbl.set_markup("<b>🎯 Focus Mode</b>")
        self.title_lbl.set_halign(Gtk.Align.START)
        root.pack_start(self.title_lbl, False, False, 0)

        self.meta_lbl = Gtk.Label()
        self.meta_lbl.set_halign(Gtk.Align.START)
        self.meta_lbl.set_line_wrap(True)
        root.pack_start(self.meta_lbl, False, False, 0)

        btn_row = Gtk.Box(spacing=6)
        root.pack_start(btn_row, False, False, 0)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", lambda _: self.refresh())
        btn_row.pack_start(refresh_btn, False, False, 0)

        copy_btn = Gtk.Button(label="Copy Focus Summary")
        copy_btn.connect("clicked", lambda _: self.copy_summary())
        btn_row.pack_start(copy_btn, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        self.view = Gtk.TextView()
        self.view.set_editable(False)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.view.set_monospace(True)
        self.buf = self.view.get_buffer()
        scroll.add(self.view)
        root.pack_start(scroll, True, True, 0)

    def _set_text(self, text):
        self.buf.set_text(text or "")

    def _get_text(self):
        start, end = self.buf.get_bounds()
        return self.buf.get_text(start, end, False)

    def refresh(self):
        if not self.project_path:
            self.meta_lbl.set_text("No project selected.")
            self._set_text("Select a project first.")
            return

        name = os.path.basename(self.project_path)
        branch = git_ops.get_current_branch(self.project_path)
        status = git_ops.get_status(self.project_path)
        active = issues.active_issue(self.project_path)

        self.title_lbl.set_markup(f"<b>🎯 Focus Mode — {name}</b>")
        self.meta_lbl.set_text(
            f"Project: {self.project_path}\n"
            f"Branch: {branch or 'unknown'}\n"
            f"Issue: {(active or {}).get('title', 'No active issue')}"
        )

        data = checklists.get_project_data(self.project_path)
        stages = data.get("stages", [])

        lines = [
            f"# Focus — {name}",
            "",
            f"Branch: {branch or 'unknown'}",
            f"Issue: {(active or {}).get('title', 'No active issue')}",
            f"Changed files: {len(status.splitlines()) if status else 0}",
            "",
            "## Current checklist",
        ]

        shown = 0
        for stage in stages:
            if active and stage.get("issue_id") and stage.get("issue_id") != active.get("id"):
                continue

            lines.append("")
            lines.append(f"### {stage.get('title', 'Untitled')}")

            for item in stage.get("items", []):
                mark = "x" if item.get("done") else " "
                lines.append(f"- [{mark}] {item.get('text', '')}")
                shown += 1

                if shown >= 12:
                    break

            if shown >= 12:
                break

        if shown == 0:
            lines.append("- No checklist items for the active issue yet.")

        cmds = project_commands.get_pinned(self.project_path)
        lines.extend(["", "## Pinned commands"])

        if cmds:
            for cmd in cmds[:8]:
                lines.append(f"- {cmd.get('name', 'Command')}: `{cmd.get('command', '')}`")
        else:
            lines.append("- No pinned project commands yet.")

        self._set_text("\n".join(lines))

    def copy_summary(self):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self._get_text(), -1)
