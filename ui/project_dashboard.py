"""Middle project dashboard — commands, repo health, activity and metrics."""
import os
import shlex
import subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, Gdk, GLib
from core import git_ops, settings, project_commands


class ProjectDashboard(Gtk.Box):
    def __init__(self, on_commands_changed=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.project_path = None
        self.on_commands_changed = on_commands_changed
        self.set_size_request(300, -1)
        self._apply_css()
        self._build()

    def _apply_css(self):
        css = b"""
        .dashboard-header { background: alpha(white, 0.04); border-bottom: 1px solid alpha(white, 0.1); padding: 10px; }
        .dashboard-card { background: alpha(white, 0.035); border: 1px solid alpha(white, 0.08); border-radius: 7px; padding: 8px; margin: 5px 8px; }
        .dashboard-title { font-size: 12px; font-weight: bold; }
        .dashboard-muted { font-size: 10px; opacity: 0.55; }
        .dashboard-value { font-size: 11px; }
        .project-command-row { border-bottom: 1px solid alpha(white, 0.06); padding: 4px; }
        .project-command-name { font-weight: bold; font-size: 11px; }
        .project-command-preview { font-family: monospace; font-size: 10px; opacity: 0.60; }
        .tiny-action-btn { font-size: 10px; padding: 1px 4px; border-radius: 4px; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _build(self):
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header.get_style_context().add_class("dashboard-header")
        self.title_lbl = Gtk.Label()
        self.title_lbl.set_markup("<b>Project Dashboard</b>")
        self.title_lbl.set_halign(Gtk.Align.START)
        header.pack_start(self.title_lbl, False, False, 0)
        self.path_lbl = Gtk.Label(label="Select a project to view dashboard")
        self.path_lbl.get_style_context().add_class("dashboard-muted")
        self.path_lbl.set_halign(Gtk.Align.START)
        self.path_lbl.set_ellipsize(Pango.EllipsizeMode.START)
        header.pack_start(self.path_lbl, False, False, 0)
        self.pack_start(header, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroll.add(self.inner)
        self.pack_start(scroll, True, True, 0)

        self.commands_box = self._card("⚡ Project Commands")
        self.commands_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.commands_box.pack_start(self.commands_content, False, False, 0)
        self.inner.pack_start(self.commands_box, False, False, 0)

        self.health_box = self._card("💚 Repo Health")
        self.health_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.health_box.pack_start(self.health_content, False, False, 0)
        self.inner.pack_start(self.health_box, False, False, 0)

        self.activity_box = self._card("🕘 Recent Activity")
        self.activity_content = Gtk.Label(label="Activity log coming soon.")
        self.activity_content.set_halign(Gtk.Align.START)
        self.activity_content.get_style_context().add_class("dashboard-muted")
        self.activity_box.pack_start(self.activity_content, False, False, 0)
        self.inner.pack_start(self.activity_box, False, False, 0)

        self.metrics_box = self._card("📊 Metrics")
        self.metrics_content = Gtk.Label(label="Metrics coming soon.")
        self.metrics_content.set_halign(Gtk.Align.START)
        self.metrics_content.get_style_context().add_class("dashboard-muted")
        self.metrics_box.pack_start(self.metrics_content, False, False, 0)
        self.inner.pack_start(self.metrics_box, False, False, 0)
        self._refresh_empty()

    def _card(self, title):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("dashboard-card")
        top = Gtk.Box(spacing=6)
        lbl = Gtk.Label()
        lbl.set_markup(f"<b>{title}</b>")
        lbl.set_halign(Gtk.Align.START)
        lbl.get_style_context().add_class("dashboard-title")
        top.pack_start(lbl, True, True, 0)
        if title.startswith("⚡"):
            add_btn = Gtk.Button(label="＋")
            add_btn.set_tooltip_text("Add a command for this project")
            add_btn.set_relief(Gtk.ReliefStyle.NONE)
            add_btn.connect("clicked", self._add_command_dialog)
            top.pack_end(add_btn, False, False, 0)
        box.pack_start(top, False, False, 0)
        return box

    def _clear(self, box):
        for child in box.get_children():
            box.remove(child)

    def _row(self, label, value):
        row = Gtk.Box(spacing=6)
        left = Gtk.Label(label=label)
        left.set_halign(Gtk.Align.START)
        left.get_style_context().add_class("dashboard-muted")
        row.pack_start(left, True, True, 0)
        right = Gtk.Label(label=value)
        right.set_halign(Gtk.Align.END)
        right.set_ellipsize(Pango.EllipsizeMode.END)
        right.get_style_context().add_class("dashboard-value")
        row.pack_end(right, False, False, 0)
        return row

    def set_project(self, path):
        self.project_path = path
        self.title_lbl.set_markup(f"<b>{os.path.basename(path)}</b>")
        self.path_lbl.set_text(path)
        self.refresh()

    def refresh(self):
        if not self.project_path:
            self._refresh_empty()
            return
        self._refresh_commands()
        self._refresh_health()
        self.show_all()

    def _refresh_empty(self):
        self._clear(self.commands_content)
        self.commands_content.pack_start(Gtk.Label(label="Select a project first."), False, False, 0)
        self._clear(self.health_content)
        self.health_content.pack_start(Gtk.Label(label="No project selected."), False, False, 0)
        self.show_all()

    def _refresh_commands(self):
        self._clear(self.commands_content)
        cmds = project_commands.list_commands(self.project_path)
        if not cmds:
            hint = Gtk.Label(label="No project commands yet. Click ＋ to add one.")
            hint.set_halign(Gtk.Align.START)
            hint.get_style_context().add_class("dashboard-muted")
            self.commands_content.pack_start(hint, False, False, 0)
            return

        for cmd in cmds:
            self.commands_content.pack_start(self._command_row(cmd), False, False, 0)

    def _command_row(self, cmd):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        outer.get_style_context().add_class("project-command-row")

        top = Gtk.Box(spacing=4)
        name = cmd.get("name", "Command")
        flags = ("⭐ " if cmd.get("pinned") else "") + ("🎯 " if cmd.get("default") else "")
        name_lbl = Gtk.Label(label=flags + name)
        name_lbl.set_halign(Gtk.Align.START)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        name_lbl.get_style_context().add_class("project-command-name")
        top.pack_start(name_lbl, True, True, 0)

        actions = [
            ("▶", "Run silently", lambda _ : self._run_command(cmd, terminal=False)),
            ("🖥", "Run in terminal", lambda _ : self._run_command(cmd, terminal=True)),
            ("📋", "Copy command", lambda _ : self._copy_command(cmd)),
            ("✏", "Edit command", lambda _ : self._edit_command_dialog(cmd)),
            ("⭐", "Pin/unpin command in sidebar", lambda _ : self._toggle_pin(cmd)),
        ]
        for label, tip, cb in actions:
            btn = Gtk.Button(label=label)
            btn.set_tooltip_text(tip)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("tiny-action-btn")
            btn.connect("clicked", cb)
            top.pack_end(btn, False, False, 0)
        outer.pack_start(top, False, False, 0)

        preview = cmd.get("command", "")[:85] + ("…" if len(cmd.get("command", "")) > 85 else "")
        prev = Gtk.Label(label=preview)
        prev.set_halign(Gtk.Align.START)
        prev.set_ellipsize(Pango.EllipsizeMode.END)
        prev.get_style_context().add_class("project-command-preview")
        outer.pack_start(prev, False, False, 0)

        move_row = Gtk.Box(spacing=4)
        for label, tip, cb in [
            ("⬆", "Move command up", lambda _ : self._move_command(cmd, -1)),
            ("⬇", "Move command down", lambda _ : self._move_command(cmd, 1)),
            ("🎯 Default", "Set as default project command", lambda _ : self._set_default(cmd)),
            ("🗑", "Delete command", lambda _ : self._delete_command(cmd)),
        ]:
            btn = Gtk.Button(label=label)
            btn.set_tooltip_text(tip)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("tiny-action-btn")
            btn.connect("clicked", cb)
            move_row.pack_start(btn, False, False, 0)
        outer.pack_start(move_row, False, False, 0)
        return outer

    def _refresh_health(self):
        self._clear(self.health_content)
        branch = git_ops.get_current_branch(self.project_path)
        status = git_ops.get_status(self.project_path)
        changed = len(status.splitlines()) if status else 0
        untracked = len([l for l in status.splitlines() if l.startswith("??")]) if status else 0
        remotes = git_ops.get_remotes(self.project_path)
        ok_commit, latest_commit = git_ops.run_custom(self.project_path, "git log -1 --pretty=%s")
        ok_stash, stash_out = git_ops.run_custom(self.project_path, "git stash list")
        ok_tags, tags_out = git_ops.run_custom(self.project_path, "git tag")
        ok_ahead, ahead_out = git_ops.run_custom(self.project_path, "git status -sb")

        self.health_content.pack_start(self._row("Branch", branch or "main"), False, False, 0)
        self.health_content.pack_start(self._row("Changed", str(changed)), False, False, 0)
        self.health_content.pack_start(self._row("Untracked", str(untracked)), False, False, 0)
        self.health_content.pack_start(self._row("Ahead/behind", self._parse_ahead_behind(ahead_out if ok_ahead else "")), False, False, 0)
        self.health_content.pack_start(self._row("Remotes", ", ".join(remotes) if remotes else "none"), False, False, 0)
        self.health_content.pack_start(self._row("Latest", latest_commit if ok_commit and latest_commit else "none"), False, False, 0)
        self.health_content.pack_start(self._row("Stashes", str(len(stash_out.splitlines())) if ok_stash and stash_out else "0"), False, False, 0)
        self.health_content.pack_start(self._row("Tags", str(len(tags_out.splitlines())) if ok_tags and tags_out else "0"), False, False, 0)

    def _parse_ahead_behind(self, status_line):
        first = (status_line or "").splitlines()[0] if status_line else ""
        if "ahead" not in first and "behind" not in first:
            return "synced/unknown"
        return first.split("[")[-1].rstrip("]")

    def _render(self, cmd):
        branch = git_ops.get_current_branch(self.project_path) if self.project_path else ""
        return project_commands.render(cmd.get("command", ""), self.project_path, branch)

    def _run_command(self, cmd, terminal=False):
        if not self.project_path:
            return
        command = self._render(cmd)
        if terminal or cmd.get("use_terminal"):
            self._run_in_terminal(command)
        else:
            git_ops.run_custom(self.project_path, command)
        self.refresh()

    def _run_in_terminal(self, command):
        cwd = self.project_path or os.path.expanduser("~")
        bash_cmd = f"cd {shlex.quote(cwd)}\n{command}\necho\necho '--- Done. Press Enter to close ---'\nread"
        term = settings.get("terminal_cmd")
        for t in [term, "kitty", "x-terminal-emulator", "gnome-terminal", "xterm"]:
            try:
                if t == "kitty":
                    subprocess.Popen(["kitty", "--hold", "bash", "-lc", bash_cmd], cwd=cwd)
                else:
                    subprocess.Popen([t, "--", "bash", "-lc", bash_cmd], cwd=cwd)
                return
            except FileNotFoundError:
                continue

    def _copy_command(self, cmd):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(self._render(cmd), -1)

    def _toggle_pin(self, cmd):
        project_commands.set_pinned(self.project_path, cmd["id"], not cmd.get("pinned"))
        self._changed()

    def _set_default(self, cmd):
        project_commands.set_default(self.project_path, cmd["id"])
        self._changed()

    def _move_command(self, cmd, direction):
        project_commands.move(self.project_path, cmd["id"], direction)
        self._changed()

    def _delete_command(self, cmd):
        dlg = Gtk.MessageDialog(transient_for=self.get_toplevel(), flags=0,
                                message_type=Gtk.MessageType.WARNING,
                                buttons=Gtk.ButtonsType.YES_NO,
                                text=f"Delete command '{cmd.get('name', 'Command')}'?")
        response = dlg.run()
        dlg.destroy()
        if response == Gtk.ResponseType.YES:
            project_commands.remove(self.project_path, cmd["id"])
            self._changed()

    def _changed(self):
        self.refresh()
        if self.on_commands_changed:
            self.on_commands_changed()

    def _add_command_dialog(self, _):
        if not self.project_path:
            return
        self._command_dialog()

    def _edit_command_dialog(self, cmd):
        self._command_dialog(cmd)

    def _command_dialog(self, cmd=None):
        editing = cmd is not None
        dlg = Gtk.Dialog(title="Edit Project Command" if editing else "Add Project Command",
                         transient_for=self.get_toplevel(), flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dlg.set_default_size(540, 330)
        box = dlg.get_content_area()
        box.set_border_width(12)
        box.set_spacing(8)

        grid = Gtk.Grid(column_spacing=10, row_spacing=8)
        name_entry = Gtk.Entry()
        name_entry.set_text((cmd or {}).get("name", ""))
        name_entry.set_placeholder_text("e.g. Run tests")
        command_view = Gtk.TextView()
        command_view.set_monospace(True)
        command_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        command_buf = command_view.get_buffer()
        command_buf.set_text((cmd or {}).get("command", ""))

        terminal_switch = Gtk.Switch()
        terminal_switch.set_active(bool((cmd or {}).get("use_terminal", False)))
        pinned_switch = Gtk.Switch()
        pinned_switch.set_active(bool((cmd or {}).get("pinned", False)))
        default_switch = Gtk.Switch()
        default_switch.set_active(bool((cmd or {}).get("default", False)))

        def lbl(text):
            l = Gtk.Label(label=text); l.set_halign(Gtk.Align.START); return l
        grid.attach(lbl("Name:"), 0, 0, 1, 1)
        grid.attach(name_entry, 1, 0, 1, 1)
        grid.attach(lbl("Terminal:"), 0, 1, 1, 1)
        grid.attach(terminal_switch, 1, 1, 1, 1)
        grid.attach(lbl("Pinned:"), 0, 2, 1, 1)
        grid.attach(pinned_switch, 1, 2, 1, 1)
        grid.attach(lbl("Default:"), 0, 3, 1, 1)
        grid.attach(default_switch, 1, 3, 1, 1)
        box.pack_start(grid, False, False, 0)

        hint = Gtk.Label(label="Variables supported: {project}, {branch}, {name}, {venv}")
        hint.set_halign(Gtk.Align.START)
        hint.get_style_context().add_class("dashboard-muted")
        box.pack_start(hint, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(100)
        scroll.add(command_view)
        box.pack_start(scroll, True, True, 0)
        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK:
            start, end = command_buf.get_bounds()
            name = name_entry.get_text().strip()
            command = command_buf.get_text(start, end, False).strip()
            if name and command:
                if editing:
                    project_commands.update(
                        self.project_path, cmd["id"],
                        name=name, command=command,
                        use_terminal=terminal_switch.get_active(),
                        pinned=pinned_switch.get_active(),
                        default=default_switch.get_active(),
                    )
                else:
                    project_commands.add(
                        self.project_path, name, command,
                        use_terminal=terminal_switch.get_active(),
                        pinned=pinned_switch.get_active(),
                        is_default=default_switch.get_active(),
                    )
                self._changed()
        dlg.destroy()