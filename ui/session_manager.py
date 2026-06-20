"""Project Session Manager."""
import os
import shlex
import subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

from core import settings, project_commands, activity
from core.code_review import generate
from ui.checklist_window import ChecklistWindow


class SessionManagerWindow(Gtk.Window):
    def __init__(self, parent, project_path, on_code_review=None):
        super().__init__(title="🚀 Launch Project Session")
        self.parent = parent
        self.project_path = os.path.abspath(os.path.expanduser(project_path))
        self.on_code_review = on_code_review
        self.set_transient_for(parent)
        self.set_default_size(560, 520)
        self._build()
        self.show_all()

    def _build(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        vbox.set_border_width(14)
        self.add(vbox)

        title = Gtk.Label()
        title.set_markup(f"<b>{os.path.basename(self.project_path)}</b>")
        title.set_halign(Gtk.Align.START)
        vbox.pack_start(title, False, False, 0)

        path = Gtk.Label(label=self.project_path)
        path.set_halign(Gtk.Align.START)
        path.set_line_wrap(True)
        path.get_style_context().add_class("dim-label")
        vbox.pack_start(path, False, False, 0)

        grid = Gtk.Grid(column_spacing=12, row_spacing=8)

        self.open_vscode = Gtk.CheckButton(label="Open VSCode")
        self.open_terminal = Gtk.CheckButton(label="Open terminal(s)")
        self.open_checklist = Gtk.CheckButton(label="Open checklist")
        self.open_readme = Gtk.CheckButton(label="Open README if found")
        self.generate_review = Gtk.CheckButton(label="Generate code review")
        self.run_default = Gtk.CheckButton(label="Run default project command")

        self.open_vscode.set_active(True)
        self.open_terminal.set_active(True)

        checks = [
            self.open_vscode,
            self.open_terminal,
            self.open_checklist,
            self.open_readme,
            self.generate_review,
            self.run_default,
        ]

        for i, check in enumerate(checks):
            grid.attach(check, 0, i, 1, 1)

        term_lbl = Gtk.Label(label="Terminals to open:")
        term_lbl.set_halign(Gtk.Align.START)
        grid.attach(term_lbl, 1, 1, 1, 1)

        self.term_spin = Gtk.SpinButton()
        self.term_spin.set_range(1, 6)
        self.term_spin.set_increments(1, 1)
        self.term_spin.set_value(2)
        grid.attach(self.term_spin, 2, 1, 1, 1)

        vbox.pack_start(grid, False, False, 0)

        default_cmd = project_commands.get_default(self.project_path)
        cmd_text = default_cmd.get("command", "") if default_cmd else ""

        default_lbl = Gtk.Label()
        default_lbl.set_markup("<b>Default command preview</b>")
        default_lbl.set_halign(Gtk.Align.START)
        vbox.pack_start(default_lbl, False, False, 0)

        cmd_scroll = Gtk.ScrolledWindow()
        cmd_scroll.set_min_content_height(90)

        self.cmd_buf = Gtk.TextBuffer()
        self.cmd_buf.set_text(cmd_text)
        self.cmd_view = Gtk.TextView(buffer=self.cmd_buf)
        self.cmd_view.set_monospace(True)
        self.cmd_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        cmd_scroll.add(self.cmd_view)
        vbox.pack_start(cmd_scroll, False, False, 0)

        btn_row = Gtk.Box(spacing=8)

        copy_btn = Gtk.Button(label="📋 Copy Default Command")
        copy_btn.connect("clicked", self._copy_default_command)
        btn_row.pack_start(copy_btn, False, False, 0)

        start_btn = Gtk.Button(label="🚀 Start Session")
        start_btn.connect("clicked", self._start_session)
        btn_row.pack_end(start_btn, False, False, 0)

        vbox.pack_end(btn_row, False, False, 0)

    def _render_command(self):
        start, end = self.cmd_buf.get_bounds()
        raw = self.cmd_buf.get_text(start, end, False).strip()
        branch = ""
        return project_commands.render(raw, self.project_path, branch)

    def _copy_default_command(self, _=None):
        command = self._render_command()
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(command, -1)
        activity.log_event(self.project_path, "command_copied", "Copied session default command", {"command": command})

    def _start_session(self, _=None):
        if self.open_vscode.get_active():
            self._open_vscode()

        if self.open_terminal.get_active():
            for _i in range(int(self.term_spin.get_value())):
                self._open_terminal()

        if self.open_checklist.get_active():
            ChecklistWindow(self.parent, self.project_path)

        if self.open_readme.get_active():
            self._open_readme()

        if self.generate_review.get_active():
            self._generate_code_review()

        if self.run_default.get_active():
            command = self._render_command()
            if command:
                self._run_terminal_command(command)

        activity.log_event(self.project_path, "session_started", "Started project session")
        self.destroy()

    def _open_vscode(self):
        try:
            subprocess.Popen([settings.get("vscode_cmd") or "code", self.project_path])
        except Exception:
            subprocess.Popen(["xdg-open", self.project_path])

    def _open_terminal(self):
        term = settings.get("terminal_cmd") or "kitty"
        for t in [term, "kitty", "x-terminal-emulator", "gnome-terminal", "xterm"]:
            try:
                subprocess.Popen([t], cwd=self.project_path)
                return
            except FileNotFoundError:
                continue

    def _open_readme(self):
        for name in ["README.md", "readme.md", "README.txt"]:
            path = os.path.join(self.project_path, name)
            if os.path.exists(path):
                try:
                    subprocess.Popen([settings.get("vscode_cmd") or "code", path])
                except Exception:
                    subprocess.Popen(["xdg-open", path])
                return

    def _generate_code_review(self):
        output_dir = os.path.expanduser(settings.get("code_review_output_dir") or "~/Projects/Code Reviews")
        os.makedirs(output_dir, exist_ok=True)
        out_path = generate(self.project_path, output_dir)
        activity.log_event(self.project_path, "code_review_generated", f"Generated code review: {out_path}")
        try:
            subprocess.Popen([settings.get("vscode_cmd") or "code", out_path])
        except Exception:
            subprocess.Popen(["xdg-open", out_path])

    def _run_terminal_command(self, command):
        bash_cmd = (
            f"cd {shlex.quote(self.project_path)}\n"
            f"{command}\n"
            "echo\n"
            "echo '--- Done. Press Enter to close ---'\n"
            "read"
        )

        term = settings.get("terminal_cmd") or "kitty"
        for t in [term, "kitty", "x-terminal-emulator", "gnome-terminal", "xterm"]:
            try:
                if t == "kitty":
                    subprocess.Popen(["kitty", "--hold", "bash", "-lc", bash_cmd], cwd=self.project_path)
                else:
                    subprocess.Popen([t, "--", "bash", "-lc", bash_cmd], cwd=self.project_path)
                activity.log_event(self.project_path, "command_terminal", "Ran session default command", {"command": command})
                return
            except FileNotFoundError:
                continue