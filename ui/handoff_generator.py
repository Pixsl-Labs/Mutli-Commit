"""Project handoff generator window."""
import os
import subprocess
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

from core import git_ops, project_commands, activity, checklists


def _run(path, command):
    try:
        result = subprocess.run(
            command,
            cwd=path,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return result.returncode == 0, (result.stdout or result.stderr or "").strip()
    except Exception as e:
        return False, str(e)


class HandoffGeneratorWindow(Gtk.Window):
    def __init__(self, parent=None, project_path=None):
        super().__init__(title="📘 Handoff Generator")
        self.parent_window = parent
        self.project_path = os.path.abspath(os.path.expanduser(project_path)) if project_path else None
        self.set_default_size(820, 620)
        self.set_position(Gtk.WindowPosition.CENTER)
        self._build()
        self.refresh_preview()
        self.show_all()

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_border_width(10)
        self.add(root)

        header = Gtk.Label()
        header.set_markup("<b>📘 Project Handoff Generator</b>")
        header.set_halign(Gtk.Align.START)
        root.pack_start(header, False, False, 0)

        self.path_lbl = Gtk.Label(label=self.project_path or "No project selected")
        self.path_lbl.set_halign(Gtk.Align.START)
        root.pack_start(self.path_lbl, False, False, 0)

        row = Gtk.Box(spacing=6)
        root.pack_start(row, False, False, 0)

        refresh_btn = Gtk.Button(label="Refresh Preview")
        refresh_btn.connect("clicked", lambda _: self.refresh_preview())
        row.pack_start(refresh_btn, False, False, 0)

        copy_btn = Gtk.Button(label="Copy Markdown")
        copy_btn.connect("clicked", lambda _: self.copy_markdown())
        row.pack_start(copy_btn, False, False, 0)

        save_btn = Gtk.Button(label="Save handoff.md")
        save_btn.connect("clicked", lambda _: self.save_handoff())
        row.pack_start(save_btn, False, False, 0)

        self.status_lbl = Gtk.Label(label="")
        self.status_lbl.set_halign(Gtk.Align.START)
        row.pack_start(self.status_lbl, True, True, 0)

        scroll = Gtk.ScrolledWindow()
        self.view = Gtk.TextView()
        self.view.set_monospace(True)
        self.view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.buf = self.view.get_buffer()
        scroll.add(self.view)
        root.pack_start(scroll, True, True, 0)

    def _set_text(self, text):
        self.buf.set_text(text or "")

    def _get_text(self):
        start, end = self.buf.get_bounds()
        return self.buf.get_text(start, end, False)

    def refresh_preview(self):
        if not self.project_path:
            self._set_text("# Handoff\n\nNo project selected.")
            return

        name = os.path.basename(self.project_path)
        branch = git_ops.get_current_branch(self.project_path)
        status = git_ops.get_status(self.project_path)
        ok_commits, commits = _run(self.project_path, "git log --oneline -8")
        ok_readme, readme = _run(self.project_path, "test -f README.md && sed -n '1,80p' README.md || true")

        cmds = project_commands.list_commands(self.project_path)
        events = activity.recent(self.project_path, limit=10)

        lines = [
            f"# {name} — Handoff",
            "",
            "## Project",
            f"- Path: `{self.project_path}`",
            f"- Branch: `{branch}`",
            f"- Changed files: `{len(status.splitlines()) if status else 0}`",
            "",
            "## Useful Commands",
        ]

        if cmds:
            for cmd in cmds:
                flag = " ⭐" if cmd.get("pinned") else ""
                lines.append(f"- **{cmd.get('name', 'Command')}**{flag}: `{cmd.get('command', '')}`")
        else:
            lines.append("- No project commands saved yet.")

        lines.extend([
            "",
            "## Recent Commits",
            commits if ok_commits and commits else "No recent commits found.",
            "",
            "## Current Git Status",
            "```text",
            status if status else "Clean working tree.",
            "```",
            "",
            "## Recent Multi-Commit Activity",
        ])

        if events:
            for event in events:
                lines.append(f"- {event.get('timestamp', '')}: {event.get('message', '')}")
        else:
            lines.append("- No activity logged yet.")

        lines.extend([
            "",
            "## README Snapshot",
            "```markdown",
            readme[:3000] if ok_readme and readme else "No README snapshot available.",
            "```",
            "",
            "## Checklist Snapshot",
        ])

        try:
            checklist_md = checklists.export_markdown(self.project_path, name)
            lines.append(checklist_md[:5000] if checklist_md.strip() else "No checklist data yet.")
        except Exception as e:
            lines.append(f"Could not export checklist snapshot: {e}")

        lines.extend([
            "",
            "## Next Chat Prompt",
            "```text",
            f"I am working on {name}. Use this handoff as context. Help me continue safely without breaking existing functionality.",
            "```",
        ])

        self._set_text("\n".join(lines))
        self.status_lbl.set_text("Preview refreshed.")

    def copy_markdown(self):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self._get_text(), -1)
        self.status_lbl.set_text("Copied handoff markdown.")

    def save_handoff(self):
        if not self.project_path:
            self.status_lbl.set_text("No project selected.")
            return

        out_path = os.path.join(self.project_path, "handoff.md")

        if os.path.exists(out_path):
            confirm = Gtk.MessageDialog(
                transient_for=self,
                flags=0,
                message_type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                text="Overwrite existing handoff.md?"
            )
            confirm.format_secondary_text(out_path)
            response = confirm.run()
            confirm.destroy()

            if response != Gtk.ResponseType.YES:
                self.status_lbl.set_text("Save cancelled.")
                return

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(self._get_text())

        activity.log_event(self.project_path, "handoff_generated", f"Generated handoff: {out_path}")
        self.status_lbl.set_text(f"Saved: {out_path}")
