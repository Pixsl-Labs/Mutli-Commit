"""Middle project dashboard — commands, repo health, activity and metrics."""
import os
import shlex
import subprocess
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib

from core import git_ops, settings, project_commands, activity


class ProjectDashboard(Gtk.Box):
    def __init__(self, on_commands_changed=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.project_path = None
        self.on_commands_changed = on_commands_changed
        self._refresh_source_id = None
        self._busy = False
        self.set_size_request(320, -1)
        self._apply_css()
        self._build()

    def _apply_css(self):
        css = b"""
        .dashboard-header {
            background: alpha(white, 0.04);
            border-bottom: 1px solid alpha(white, 0.10);
            padding: 10px;
        }
        .dashboard-card {
            background: alpha(white, 0.035);
            border: 1px solid alpha(white, 0.08);
            border-radius: 7px;
            padding: 8px;
            margin: 6px 8px;
        }
        .dashboard-title { font-size: 12px; font-weight: bold; }
        .dashboard-muted { font-size: 10px; opacity: 0.58; }
        .dashboard-value { font-size: 11px; }
        .project-command-row {
            border-bottom: 1px solid alpha(white, 0.06);
            padding: 4px;
        }
        .project-command-name { font-weight: bold; font-size: 11px; }
        .project-command-preview {
            font-family: monospace;
            font-size: 10px;
            opacity: 0.60;
        }
        .tiny-action-btn {
            font-size: 10px;
            padding: 1px 4px;
            border-radius: 4px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build(self):
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        header.get_style_context().add_class("dashboard-header")

        self.title_lbl = Gtk.Label()
        self.title_lbl.set_markup("<b>Project Dashboard</b>")
        self.title_lbl.set_halign(Gtk.Align.START)
        self.title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        header.pack_start(self.title_lbl, False, False, 0)

        self.path_lbl = Gtk.Label(label="Select a project")
        self.path_lbl.set_halign(Gtk.Align.START)
        self.path_lbl.set_ellipsize(Pango.EllipsizeMode.START)
        self.path_lbl.get_style_context().add_class("dashboard-muted")
        header.pack_start(self.path_lbl, False, False, 0)

        self.pack_start(header, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        scroll.add(self.inner)
        self.pack_start(scroll, True, True, 0)

        self._build_commands_card()
        self._build_repo_health_card()
        self._build_activity_card()
        self._build_metrics_card()

    def _card(self, title):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.get_style_context().add_class("dashboard-card")

        lbl = Gtk.Label(label=title)
        lbl.set_halign(Gtk.Align.START)
        lbl.get_style_context().add_class("dashboard-title")
        card.pack_start(lbl, False, False, 0)

        self.inner.pack_start(card, False, False, 0)
        return card

    def _build_commands_card(self):
        card = self._card("⚡ Project Commands")

        top = Gtk.Box(spacing=6)
        add_btn = Gtk.Button(label="+ Add")
        add_btn.get_style_context().add_class("tiny-action-btn")
        add_btn.connect("clicked", self._add_command)
        top.pack_start(add_btn, False, False, 0)

        refresh_btn = Gtk.Button(label="↻")
        refresh_btn.get_style_context().add_class("tiny-action-btn")
        refresh_btn.connect("clicked", lambda _: self.refresh())
        top.pack_end(refresh_btn, False, False, 0)

        card.pack_start(top, False, False, 0)

        self.commands_list = Gtk.ListBox()
        self.commands_list.set_selection_mode(Gtk.SelectionMode.NONE)
        card.pack_start(self.commands_list, False, False, 0)

    def _build_repo_health_card(self):
        card = self._card("🩺 Repo Health")
        self.repo_health_lbl = Gtk.Label(label="No project selected.")
        self.repo_health_lbl.set_halign(Gtk.Align.START)
        self.repo_health_lbl.set_line_wrap(True)
        self.repo_health_lbl.get_style_context().add_class("dashboard-value")
        card.pack_start(self.repo_health_lbl, False, False, 0)

    def _build_activity_card(self):
        card = self._card("🕒 Recent Activity")
        self.activity_list = Gtk.ListBox()
        self.activity_list.set_selection_mode(Gtk.SelectionMode.NONE)
        card.pack_start(self.activity_list, False, False, 0)

    def _build_metrics_card(self):
        card = self._card("📊 Metrics")
        self.metrics_lbl = Gtk.Label(label="No metrics yet.")
        self.metrics_lbl.set_halign(Gtk.Align.START)
        self.metrics_lbl.set_line_wrap(True)
        self.metrics_lbl.get_style_context().add_class("dashboard-value")
        card.pack_start(self.metrics_lbl, False, False, 0)

    def set_project(self, path):
        self.project_path = os.path.abspath(os.path.expanduser(path)) if path else None

        if self.project_path:
            self.title_lbl.set_markup(f"<b>{os.path.basename(self.project_path)}</b>")
            self.path_lbl.set_text(self.project_path)
            activity.log_event(self.project_path, "project_opened", "Opened project dashboard")
        else:
            self.title_lbl.set_markup("<b>Project Dashboard</b>")
            self.path_lbl.set_text("Select a project")

        self.refresh()
        self._start_refresh_timer()

    def _start_refresh_timer(self):
        if self._refresh_source_id:
            GLib.source_remove(self._refresh_source_id)
            self._refresh_source_id = None

        interval = int(settings.get("dashboard_refresh_interval") or 60)

        if interval <= 0:
            return

        self._refresh_source_id = GLib.timeout_add_seconds(interval, self._timer_refresh)

    def _timer_refresh(self):
        if self.project_path and not self._busy:
            self.refresh()
        return True

    def refresh(self):
        self._refresh_commands()
        self._refresh_repo_health()
        self._refresh_activity()
        self._refresh_metrics()

    def _refresh_commands(self):
        for child in self.commands_list.get_children():
            self.commands_list.remove(child)

        if not self.project_path:
            self._empty_row(self.commands_list, "Select a project first.")
            self.commands_list.show_all()
            return

        commands = project_commands.list_commands(self.project_path)

        if not commands:
            self._empty_row(self.commands_list, "No project commands yet. Add one.")
            self.commands_list.show_all()
            return

        for cmd in commands:
            self.commands_list.add(self._make_command_row(cmd))

        self.commands_list.show_all()

    def _empty_row(self, list_box, text):
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        lbl = Gtk.Label(label=text)
        lbl.set_margin_top(6)
        lbl.set_margin_bottom(6)
        lbl.get_style_context().add_class("dashboard-muted")
        row.add(lbl)
        list_box.add(row)

    def _make_command_row(self, cmd):
        row = Gtk.ListBoxRow()
        row.command_id = cmd.get("id")
        row.get_style_context().add_class("project-command-row")

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        outer.set_border_width(4)

        title = cmd.get("name", "Command")
        badges = []
        if cmd.get("default"):
            badges.append("default")
        if cmd.get("pinned"):
            badges.append("pinned")

        name_lbl = Gtk.Label(label=title + (f"  ·  {', '.join(badges)}" if badges else ""))
        name_lbl.set_halign(Gtk.Align.START)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        name_lbl.get_style_context().add_class("project-command-name")
        outer.pack_start(name_lbl, False, False, 0)

        preview = project_commands.render(cmd.get("command", ""), self.project_path, self._branch())
        preview_lbl = Gtk.Label(label=preview)
        preview_lbl.set_halign(Gtk.Align.START)
        preview_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        preview_lbl.get_style_context().add_class("project-command-preview")
        outer.pack_start(preview_lbl, False, False, 0)

        btns = Gtk.Box(spacing=4)

        for label, cb in [
            ("Run", lambda _, c=cmd: self._run_command(c, terminal=False)),
            ("Terminal", lambda _, c=cmd: self._run_command(c, terminal=True)),
            ("Copy", lambda _, c=cmd: self._copy_command(c)),
            ("Edit", lambda _, c=cmd: self._edit_command(c)),
            ("Pin", lambda _, c=cmd: self._toggle_pin(c)),
            ("Default", lambda _, c=cmd: self._set_default(c)),
            ("↑", lambda _, c=cmd: self._move_command(c, -1)),
            ("↓", lambda _, c=cmd: self._move_command(c, 1)),
            ("Del", lambda _, c=cmd: self._delete_command(c)),
        ]:
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class("tiny-action-btn")
            btn.connect("clicked", cb)
            btns.pack_start(btn, False, False, 0)

        outer.pack_start(btns, False, False, 0)
        row.add(outer)
        return row

    def _branch(self):
        if not self.project_path:
            return ""
        return git_ops.get_current_branch(self.project_path)

    def _run_command(self, cmd, terminal=False):
        if not self.project_path:
            return

        rendered = project_commands.render(cmd.get("command", ""), self.project_path, self._branch())
        if not rendered.strip():
            return

        self._busy = True
        activity.log_event(self.project_path, "command_run", cmd.get("name", rendered[:80]))

        if terminal or cmd.get("use_terminal"):
            self._open_terminal(rendered)
            self._busy = False
            return

        ok, out = git_ops.run_custom(self.project_path, rendered)
        activity.log_event(
            self.project_path,
            "command_success" if ok else "command_failed",
            f"{cmd.get('name', 'Command')}: {(out or '')[:120]}",
        )
        self._busy = False
        self.refresh()

    def _open_terminal(self, command):
        cwd = self.project_path or os.path.expanduser("~")
        bash_cmd = (
            f"cd {shlex.quote(cwd)}\n"
            f"echo {shlex.quote('Command ready. Press Enter to run:')}\n"
            f"read -e -i {shlex.quote(command)} -p '$ ' user_cmd\n"
            "eval \"$user_cmd\"\n"
            "echo\n"
            "echo '--- Done. Press Enter to close ---'\n"
            "read"
        )

        attempts = [
            ["kitty", "--hold", "bash", "-lc", bash_cmd],
            ["x-terminal-emulator", "--", "bash", "-lc", bash_cmd],
            ["gnome-terminal", "--", "bash", "-lc", bash_cmd],
            ["xterm", "-e", "bash", "-lc", bash_cmd],
        ]

        for launch in attempts:
            try:
                subprocess.Popen(launch, cwd=cwd)
                return
            except FileNotFoundError:
                continue

    def _copy_command(self, cmd):
        rendered = project_commands.render(cmd.get("command", ""), self.project_path, self._branch())
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(rendered, -1)
        activity.log_event(self.project_path, "command_copied", cmd.get("name", rendered[:80]))

    def _command_dialog(self, title, cmd=None):
        dlg = Gtk.Dialog(title=title, transient_for=self.get_toplevel(), flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        dlg.set_default_size(520, 360)

        box = dlg.get_content_area()
        box.set_border_width(12)
        box.set_spacing(8)

        name = Gtk.Entry()
        name.set_placeholder_text("Name, e.g. Run SentinelIR")
        name.set_text((cmd or {}).get("name", ""))
        box.pack_start(Gtk.Label(label="Name:"), False, False, 0)
        box.pack_start(name, False, False, 0)

        command_view = Gtk.TextView()
        command_view.set_monospace(True)
        command_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        command_buf = command_view.get_buffer()
        command_buf.set_text((cmd or {}).get("command", ""))

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(120)
        scroll.add(command_view)

        box.pack_start(Gtk.Label(label="Command:"), False, False, 0)
        box.pack_start(scroll, True, True, 0)

        flags = Gtk.Box(spacing=10)
        use_terminal = Gtk.CheckButton(label="Run in terminal")
        use_terminal.set_active(bool((cmd or {}).get("use_terminal")))
        pinned = Gtk.CheckButton(label="Pin to sidebar")
        pinned.set_active(bool((cmd or {}).get("pinned")))
        is_default = Gtk.CheckButton(label="Default")
        is_default.set_active(bool((cmd or {}).get("default")))
        flags.pack_start(use_terminal, False, False, 0)
        flags.pack_start(pinned, False, False, 0)
        flags.pack_start(is_default, False, False, 0)
        box.pack_start(flags, False, False, 0)

        dlg.show_all()
        response = dlg.run()

        start, end = command_buf.get_bounds()
        data = {
            "name": name.get_text().strip(),
            "command": command_buf.get_text(start, end, False).strip(),
            "use_terminal": use_terminal.get_active(),
            "pinned": pinned.get_active(),
            "default": is_default.get_active(),
        }
        dlg.destroy()
        return response, data

    def _add_command(self, _=None):
        if not self.project_path:
            return

        response, data = self._command_dialog("Add Project Command")
        if response == Gtk.ResponseType.OK and data["command"]:
            project_commands.add(
                self.project_path,
                data["name"] or "New Command",
                data["command"],
                data["use_terminal"],
                data["pinned"],
                data["default"],
            )
            activity.log_event(self.project_path, "command_added", data["name"] or data["command"][:80])
            self.refresh()
            self._commands_changed()

    def _edit_command(self, cmd):
        response, data = self._command_dialog("Edit Project Command", cmd)
        if response == Gtk.ResponseType.OK and data["command"]:
            project_commands.update(self.project_path, cmd.get("id"), **data)
            activity.log_event(self.project_path, "command_edited", data["name"] or data["command"][:80])
            self.refresh()
            self._commands_changed()

    def _delete_command(self, cmd):
        project_commands.remove(self.project_path, cmd.get("id"))
        activity.log_event(self.project_path, "command_deleted", cmd.get("name", "Command"))
        self.refresh()
        self._commands_changed()

    def _toggle_pin(self, cmd):
        project_commands.update(self.project_path, cmd.get("id"), pinned=not bool(cmd.get("pinned")))
        self.refresh()
        self._commands_changed()

    def _set_default(self, cmd):
        project_commands.set_default(self.project_path, cmd.get("id"))
        self.refresh()
        self._commands_changed()

    def _move_command(self, cmd, direction):
        project_commands.move(self.project_path, cmd.get("id"), direction)
        self.refresh()
        self._commands_changed()

    def _commands_changed(self):
        if self.on_commands_changed:
            self.on_commands_changed()

    def _refresh_repo_health(self):
        if not self.project_path:
            self.repo_health_lbl.set_text("No project selected.")
            return

        health = repo_health(self.project_path)
        self.repo_health_lbl.set_text(
            f"Branch: {health['branch']}\n"
            f"Changed files: {health['changed']}\n"
            f"Untracked files: {health['untracked']}\n"
            f"Ahead/behind: +{health['ahead']} / -{health['behind']}\n"
            f"Latest commit: {health['latest_commit']}\n"
            f"Remotes: {health['remotes']}\n"
            f"Stashes: {health['stashes']}\n"
            f"Tags: {health['tags']}"
        )

    def _refresh_activity(self):
        for child in self.activity_list.get_children():
            self.activity_list.remove(child)

        if not self.project_path:
            self._empty_row(self.activity_list, "No project selected.")
            self.activity_list.show_all()
            return

        events = activity.recent(self.project_path, limit=8)

        if not events:
            self._empty_row(self.activity_list, "No activity yet.")
            self.activity_list.show_all()
            return

        for event in events:
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            msg = f"{event.get('timestamp', '')[-8:]}  {event.get('message', '')}"
            lbl = Gtk.Label(label=msg)
            lbl.set_halign(Gtk.Align.START)
            lbl.set_ellipsize(Pango.EllipsizeMode.END)
            lbl.get_style_context().add_class("dashboard-muted")
            lbl.set_margin_top(3)
            lbl.set_margin_bottom(3)
            row.add(lbl)
            self.activity_list.add(row)

        self.activity_list.show_all()

    def _refresh_metrics(self):
        if not self.project_path:
            self.metrics_lbl.set_text("No metrics yet.")
            return

        m = activity.metrics(self.project_path, days=7)
        self.metrics_lbl.set_text(
            f"Last 7 days:\n"
            f"Commits: {m.get('commits', 0)}\n"
            f"Pushes: {m.get('pushes', 0)}\n"
            f"Commands: {m.get('commands', 0)}\n"
            f"Checklists: {m.get('checklists', 0)}\n"
            f"Code reviews: {m.get('code_reviews', 0)}"
        )


def _run(path, command):
    ok, out = git_ops.run_custom(path, command)
    return out.strip() if ok and out else ""


def repo_health(path):
    branch = git_ops.get_current_branch(path)
    status = git_ops.get_status(path) or ""
    lines = status.splitlines()

    changed = len(lines)
    untracked = sum(1 for line in lines if line.startswith("??"))

    ahead = 0
    behind = 0
    raw = _run(path, "git rev-list --left-right --count @{u}...HEAD 2>/dev/null")
    if raw:
        try:
            behind, ahead = [int(x) for x in raw.split()[:2]]
        except Exception:
            ahead, behind = 0, 0

    latest = _run(path, "git log -1 --pretty=%s") or "No commits"
    remotes = _run(path, "git remote") or "none"
    stashes_raw = _run(path, "git stash list")
    stashes = len(stashes_raw.splitlines()) if stashes_raw else 0
    tags_raw = _run(path, "git tag")
    tags = len(tags_raw.splitlines()) if tags_raw else 0

    return {
        "branch": branch,
        "changed": changed,
        "untracked": untracked,
        "ahead": ahead,
        "behind": behind,
        "latest_commit": latest,
        "remotes": ", ".join(remotes.splitlines()) if remotes != "none" else "none",
        "stashes": stashes,
        "tags": tags,
    }


# ── Multi-Commit project command safety patch ───────────────────────────────
try:
    from gi.repository import Gtk
    from core import command_safety
except Exception:
    Gtk = None
    command_safety = None


def _mc_dashboard_confirm_risky_command(self, command):
    if Gtk is None or command_safety is None:
        return True

    if not command_safety.is_dangerous(command):
        return True

    dlg = Gtk.MessageDialog(
        transient_for=self.get_toplevel(),
        flags=0,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.YES_NO,
        text="Risky project command detected"
    )
    dlg.format_secondary_text(command_safety.warning_text(command))
    response = dlg.run()
    dlg.destroy()
    return response == Gtk.ResponseType.YES


if not getattr(ProjectDashboard, "_mc_project_command_safety_patch_applied", False):
    ProjectDashboard._mc_base_run_command = getattr(ProjectDashboard, "_run_command", None)

    def _mc_safe_run_command(self, cmd, terminal=False):
        command = ""

        try:
            command = self._render(cmd)
        except Exception:
            command = cmd.get("command", "") if isinstance(cmd, dict) else ""

        if command and not self._mc_dashboard_confirm_risky_command(command):
            try:
                activity.log_event(self.project_path, "command_cancelled", f"Cancelled risky command: {cmd.get('name', command[:60])}")
                self.refresh()
            except Exception:
                pass
            return

        if ProjectDashboard._mc_base_run_command:
            return ProjectDashboard._mc_base_run_command(self, cmd, terminal=terminal)

    ProjectDashboard._run_command = _mc_safe_run_command
    ProjectDashboard._mc_dashboard_confirm_risky_command = _mc_dashboard_confirm_risky_command
    ProjectDashboard._mc_project_command_safety_patch_applied = True

