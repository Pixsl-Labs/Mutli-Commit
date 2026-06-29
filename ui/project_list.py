"""Left panel — grouped project list with one-click actions and advanced context menu."""
import os
import subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, Gdk
from core import project_groups, project_commands, settings, vscode_reset
from core.git_ops import is_git_repo, get_status, get_current_branch, run_custom
from ui.checklist_window import ChecklistWindow
from ui.session_manager import SessionManagerWindow

STATUS_CLEAN    = "🟢"
STATUS_UNSTAGED = "🟡"
STATUS_CONFLICT = "🔴"


def _get_status_icon(path):
    if not is_git_repo(path):
        return ""
    s = get_status(path)
    if not s:
        return STATUS_CLEAN
    if "U" in s or "AA" in s or "DD" in s:
        return STATUS_CONFLICT
    return STATUS_UNSTAGED

def _open_vscode_path(path):
    """Open a project path in VSCode with xdg-open fallback."""
    path = os.path.abspath(os.path.expanduser(path))
    cmd = settings.get("vscode_cmd") or "code"

    try:
        subprocess.Popen([cmd, path])
    except Exception:
        try:
            subprocess.Popen(["xdg-open", path])
        except Exception:
            pass


class ProjectListPanel(Gtk.Box):
    def __init__(self, on_select, on_code_review=None):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.on_select = on_select
        self.on_code_review = on_code_review
        self.selected_path = None
        self._apply_css()
        self._build()
        self.refresh()

    def _apply_css(self):
        css = b"""
        .project-row { border-bottom: 1px solid alpha(white, 0.07); }
        .project-row:selected { background: linear-gradient(90deg, #c0392b, #922b21); }
        .project-name { font-size: 13px; font-weight: bold; }
        .project-path { font-size: 10px; opacity: 0.55; }
        .git-badge {
            background: #27ae60; color: white;
            border-radius: 3px; padding: 0 4px;
            font-size: 10px;
        }
        .status-clean    { color: #2ecc71; }
        .status-unstaged { color: #f39c12; }
        .status-conflict { color: #e74c3c; }
        .branch-label { font-size: 10px; color: #3498db; }
        .action-btn {
            padding: 2px 6px; font-size: 11px;
            border-radius: 4px;
            border: 1px solid alpha(white, 0.15);
        }
        .panel-header {
            background: alpha(white, 0.04);
            border-bottom: 1px solid alpha(white, 0.1);
            padding: 8px;
        }
        .group-row {
            background: alpha(white, 0.035);
            border-bottom: 1px solid alpha(white, 0.09);
        }
        .group-title { font-weight: bold; font-size: 12px; }
        .pinned-row { background: alpha(#f1c40f, 0.06); }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build(self):
        hdr = Gtk.Box(spacing=6)
        hdr.get_style_context().add_class("panel-header")
        lbl = Gtk.Label()
        lbl.set_markup("<b>Projects</b>")
        lbl.set_halign(Gtk.Align.START)
        hdr.pack_start(lbl, True, True, 0)

        add_group_btn = Gtk.Button(label="+ Group")
        add_group_btn.set_tooltip_text("Create a collapsible project group")
        add_group_btn.set_relief(Gtk.ReliefStyle.NONE)
        add_group_btn.connect("clicked", self._add_group_dialog)
        hdr.pack_end(add_group_btn, False, False, 0)

        add_btn = Gtk.Button(label="+ Project")
        add_btn.set_tooltip_text("Add a project folder to Multi-Commit")
        add_btn.connect("clicked", lambda _: self.open_folder_dialog())
        hdr.pack_end(add_btn, False, False, 0)

        refresh_btn = Gtk.Button(label="↻")
        refresh_btn.set_tooltip_text("Refresh project Git status indicators")
        refresh_btn.set_relief(Gtk.ReliefStyle.NONE)
        refresh_btn.connect("clicked", lambda _: self.refresh())
        hdr.pack_end(refresh_btn, False, False, 0)
        self.pack_start(hdr, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("key-press-event", self._on_key_press)
        self.list_box.connect("row-selected", self._on_row_selected)
        self.list_box.connect("button-press-event", self._on_button_press)
        scroll.add(self.list_box)
        self.pack_start(scroll, True, True, 0)

    def refresh(self):
        selected = self.selected_path
        for child in self.list_box.get_children():
            self.list_box.remove(child)

        data = project_groups.load()
        pinned = [p for p in data.get("pinned_projects", []) if os.path.exists(p)]
        if pinned:
            self.list_box.add(self._make_group_row({"id": "__pinned__", "name": "⭐ Pinned", "collapsed": False}, is_pinned_header=True))
            for path in pinned:
                self.list_box.add(self._make_row(path, pinned_style=True))

        groups = data.get("groups", [])
        if not groups:
            self._add_empty_row()
        else:
            any_project = bool(pinned)
            for group in groups:
                self.list_box.add(self._make_group_row(group))
                if not group.get("collapsed"):
                    for path in group.get("projects", []):
                        any_project = True
                        self.list_box.add(self._make_row(path))
            if not any_project:
                self._add_empty_row()

        self.list_box.show_all()

        if selected:
            for row in self.list_box.get_children():
                if getattr(row, "path", None) == selected:
                    self.list_box.select_row(row)
                    break

    def _add_empty_row(self):
        lbl = Gtk.Label(label="No projects yet.\nClick '+ Project' to add one.")
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_margin_top(20)
        row = Gtk.ListBoxRow()
        row.add(lbl)
        row.set_selectable(False)
        self.list_box.add(row)

    def _make_group_row(self, group, is_pinned_header=False):
        row = Gtk.ListBoxRow()
        row.group_id = group.get("id")
        row.is_group = True
        row.set_selectable(False)
        row.get_style_context().add_class("group-row")

        box = Gtk.Box(spacing=6)
        box.set_border_width(7)
        arrow = "▸" if group.get("collapsed") else "▾"
        lbl = Gtk.Label(label=("" if is_pinned_header else arrow + " ") + group.get("name", "Projects"))
        lbl.set_halign(Gtk.Align.START)
        lbl.get_style_context().add_class("group-title")
        box.pack_start(lbl, True, True, 0)

        if not is_pinned_header:
            count = len(group.get("projects", []))
            count_lbl = Gtk.Label(label=str(count))
            count_lbl.get_style_context().add_class("dim-label")
            box.pack_end(count_lbl, False, False, 0)

        row.add(box)
        return row

    def _make_row(self, path, pinned_style=False):
        row = Gtk.ListBoxRow()
        row.path = path
        row.get_style_context().add_class("project-row")
        if pinned_style:
            row.get_style_context().add_class("pinned-row")

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        vbox.set_border_width(8)

        top = Gtk.Box(spacing=6)
        status_icon = _get_status_icon(path)
        status_lbl = Gtk.Label(label=status_icon)
        status_lbl.set_tooltip_text("Git status: green clean, amber changed, red conflicts")
        top.pack_start(status_lbl, False, False, 0)

        name = Gtk.Label(label=os.path.basename(path))
        name.set_halign(Gtk.Align.START)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.set_max_width_chars(20)
        name.get_style_context().add_class("project-name")
        top.pack_start(name, True, True, 0)

        if project_groups.is_pinned(path):
            pin_lbl = Gtk.Label(label="⭐")
            pin_lbl.set_tooltip_text("Pinned project")
            top.pack_end(pin_lbl, False, False, 0)

        if is_git_repo(path):
            badge = Gtk.Label(label=" git ")
            badge.get_style_context().add_class("git-badge")
            badge.set_tooltip_text("This folder is a Git repository")
            top.pack_end(badge, False, False, 0)

            branch = get_current_branch(path)
            branch_lbl = Gtk.Label(label=f"  {branch}")
            branch_lbl.get_style_context().add_class("branch-label")
            branch_lbl.set_tooltip_text("Current Git branch")
            top.pack_end(branch_lbl, False, False, 0)

        vbox.pack_start(top, False, False, 0)

        path_lbl = Gtk.Label(label=path)
        path_lbl.set_halign(Gtk.Align.START)
        path_lbl.set_ellipsize(Pango.EllipsizeMode.START)
        path_lbl.set_max_width_chars(32)
        path_lbl.get_style_context().add_class("project-path")
        path_lbl.set_tooltip_text(path)
        vbox.pack_start(path_lbl, False, False, 0)

        btn_box = Gtk.Box(spacing=4)
        btn_box.set_margin_top(4)

        for label, tip, cb in [
            ("📁 Folder",   "Open this project folder in the file manager", lambda _, p=path: self._open_folder(p)),
            ("💻 VSCode",   "Open this project in VSCode",                 lambda _, p=path: self._open_vscode(p)),
            ("🖥 Terminal", "Open a terminal in this project folder",       lambda _, p=path: self._open_terminal(p)),
            ("📋 Review",   "Generate a markdown code review for this project", lambda _, p=path: self._code_review(p)),
            ("✅ Checklist", "Open this project's roadmap/checklist",       lambda _, p=path: self._open_checklist(p)),
            ("🚀 Session", "Launch project session manager", lambda _, p=path: self._open_session(p)),
        ]:
            btn = Gtk.Button(label=label)
            btn.set_tooltip_text(tip)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("action-btn")
            btn.connect("clicked", cb)
            btn_box.pack_start(btn, False, False, 0)

        rm = Gtk.Button(label="✕")
        rm.set_tooltip_text("Remove this project from Multi-Commit only. Files are not deleted.")
        rm.set_relief(Gtk.ReliefStyle.NONE)
        rm.connect("clicked", lambda _, p=path: self._remove(p))
        btn_box.pack_end(rm, False, False, 0)

        vbox.pack_start(btn_box, False, False, 0)

        pinned_commands = project_commands.get_pinned(path)
        if pinned_commands:
            pinned_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            pinned_box.set_margin_top(4)
            for cmd in pinned_commands[:4]:
                cbtn = Gtk.Button(label=f"⭐ {cmd.get('name', 'Command')}")
                cbtn.set_tooltip_text(cmd.get("command", ""))
                cbtn.set_relief(Gtk.ReliefStyle.NONE)
                cbtn.get_style_context().add_class("action-btn")
                cbtn.connect("clicked", lambda _, p=path, c=cmd: self._run_pinned_command(p, c))
                pinned_box.pack_start(cbtn, False, False, 0)
            vbox.pack_start(pinned_box, False, False, 0)

        row.add(vbox)
        return row

    def _on_row_selected(self, listbox, row):
        if row and hasattr(row, "path"):
            self.selected_path = row.path
            self.on_select(row.path)

    def open_folder_dialog(self, group_id=None):
        dlg = Gtk.FileChooserDialog(
            title="Select Project Folder",
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        )
        dlg.set_current_folder(os.path.expanduser("~/Projects"))
        if dlg.run() == Gtk.ResponseType.OK:
            path = dlg.get_filename()
            project_groups.add_project(path, group_id=group_id)
            self.refresh()
            self.on_select(path)
        dlg.destroy()

    def _add_group_dialog(self, _):
        dlg = Gtk.Dialog(title="Add Project Group", transient_for=self.get_toplevel(), flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        box = dlg.get_content_area()
        box.set_border_width(12)
        entry = Gtk.Entry()
        entry.set_placeholder_text("e.g. Dissertation, Tools, LifeWise")
        entry.set_activates_default(True)
        box.pack_start(Gtk.Label(label="Group name:"), False, False, 0)
        box.pack_start(entry, False, False, 0)
        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name:
                project_groups.add_group(name)
                self.refresh()
        dlg.destroy()

    def _open_folder(self, path):
        subprocess.Popen(["xdg-open", path])

    def _open_vscode(self, path):
        _open_vscode_path(path)

    def _open_terminal(self, path):
        term = settings.get("terminal_cmd")
        for t in [term, "kitty", "x-terminal-emulator", "gnome-terminal", "xterm"]:
            try:
                subprocess.Popen([t], cwd=path)
                return
            except FileNotFoundError:
                continue

    def _open_session(self, path):
        win = SessionManagerWindow(self.get_toplevel(), path)
        win.show_all()

    def _code_review(self, path):
        if self.on_code_review:
            self.on_code_review(path)

    def _remove(self, path):
        project_groups.remove_project(path)
        self.refresh()

    def _open_checklist(self, path):
        win = ChecklistWindow(self.get_toplevel(), path)
        win.show_all()

    def _run_pinned_command(self, path, cmd):
        branch = get_current_branch(path) if is_git_repo(path) else ""
        rendered = project_commands.render(cmd.get("command", ""), path, branch)
        if cmd.get("use_terminal"):
            term = settings.get("terminal_cmd")
            for t in [term, "kitty", "x-terminal-emulator", "gnome-terminal", "xterm"]:
                try:
                    if t == "kitty":
                        subprocess.Popen(["kitty", "--hold", "bash", "-lc", rendered], cwd=path)
                    else:
                        subprocess.Popen([t, "--", "bash", "-lc", rendered], cwd=path)
                    return
                except FileNotFoundError:
                    continue
        else:
            run_custom(path, rendered)

    def _on_key_press(self, widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        shift = event.state & Gdk.ModifierType.SHIFT_MASK
        if ctrl and shift and event.keyval == Gdk.KEY_Delete:
            row = self.list_box.get_selected_row()
            if row and hasattr(row, "path"):
                self._remove(row.path)
            return True
        return False

    def _on_button_press(self, widget, event):
        row = self.list_box.get_row_at_y(int(event.y))
        if event.button == 1 and row and hasattr(row, "group_id") and not getattr(row, "path", None):
            if row.group_id != "__pinned__":
                project_groups.toggle_group(row.group_id)
                self.refresh()
            return True
        if event.button == 3 and row:
            if hasattr(row, "path"):
                self._project_context_menu(row.path, event)
                return True
            if hasattr(row, "group_id") and row.group_id != "__pinned__":
                self._group_context_menu(row.group_id, event)
                return True
        return False

    def _project_context_menu(self, path, event):
        menu = Gtk.Menu()

        def add(label, cb):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", cb)
            menu.append(item)

        add("📁 Open Folder", lambda _: self._open_folder(path))
        add("💻 Open in VSCode", lambda _: self._open_vscode(path))
        add("🧹 Reset VSCode", lambda _: self._reset_vscode(path))
        add("🖥 Open Terminal", lambda _: self._open_terminal(path))
        add("✅ Open Checklist", lambda _: self._open_checklist(path))
        add("📋 Generate Code Review", lambda _: self._code_review(path))
        menu.append(Gtk.SeparatorMenuItem())
        add("⭐ Unpin Project" if project_groups.is_pinned(path) else "⭐ Pin Project",
            lambda _: self._toggle_pin(path))
        add("✏ Update Project Path", lambda _: self._update_project_path(path))
        add("⬆ Move Up", lambda _: self._move_project(path, -1))
        add("⬇ Move Down", lambda _: self._move_project(path, 1))

        groups_menu = Gtk.Menu()
        groups_item = Gtk.MenuItem(label="➡ Move to Group")
        groups_item.set_submenu(groups_menu)
        for group in project_groups.groups():
            gi = Gtk.MenuItem(label=group.get("name", "Projects"))
            gi.connect("activate", lambda _, gid=group.get("id"): self._move_to_group(path, gid))
            groups_menu.append(gi)
        menu.append(groups_item)

        menu.append(Gtk.SeparatorMenuItem())
        add("✕ Remove from List", lambda _: self._remove(path))
        menu.show_all()
        menu.popup_at_pointer(event)

    def _group_context_menu(self, group_id, event):
        menu = Gtk.Menu()

        def add(label, cb):
            item = Gtk.MenuItem(label=label)
            item.connect("activate", cb)
            menu.append(item)

        add("➕ Add Project to Group", lambda _: self.open_folder_dialog(group_id=group_id))
        add("✏ Rename Group", lambda _: self._rename_group(group_id))
        add("▾ Collapse / Expand", lambda _: (project_groups.toggle_group(group_id), self.refresh()))
        add("🗑 Delete Group", lambda _: self._delete_group(group_id))
        menu.show_all()
        menu.popup_at_pointer(event)

    def _toggle_pin(self, path):
        if project_groups.is_pinned(path):
            project_groups.unpin_project(path)
        else:
            project_groups.pin_project(path)
        self.refresh()

    def _move_project(self, path, direction):
        project_groups.move_project(path, direction)
        self.refresh()

    def _move_to_group(self, path, group_id):
        project_groups.move_project_to_group(path, group_id)
        self.refresh()

    def _update_project_path(self, old_path):
        dlg = Gtk.FileChooserDialog(
            title="Choose Updated Project Folder",
            transient_for=self.get_toplevel(),
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        )
        if os.path.exists(old_path):
            dlg.set_current_folder(old_path)
        else:
            dlg.set_current_folder(os.path.expanduser("~/Projects"))
        if dlg.run() == Gtk.ResponseType.OK:
            new_path = dlg.get_filename()
            project_groups.update_project_path(old_path, new_path)
            self.selected_path = new_path
            self.refresh()
            self.on_select(new_path)
        dlg.destroy()

    def _rename_group(self, group_id):
        group = project_groups.find_group(group_id)
        if not group:
            return
        dlg = Gtk.Dialog(title="Rename Group", transient_for=self.get_toplevel(), flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        box = dlg.get_content_area()
        box.set_border_width(12)
        entry = Gtk.Entry()
        entry.set_text(group.get("name", "Projects"))
        entry.set_activates_default(True)
        box.pack_start(Gtk.Label(label="Group name:"), False, False, 0)
        box.pack_start(entry, False, False, 0)
        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()
        if dlg.run() == Gtk.ResponseType.OK:
            project_groups.rename_group(group_id, entry.get_text())
            self.refresh()
        dlg.destroy()

    def _delete_group(self, group_id):
        dlg = Gtk.MessageDialog(
            transient_for=self.get_toplevel(), flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Delete this group?"
        )
        dlg.format_secondary_text("Projects will be moved back into the default group. Files are not deleted.")
        if dlg.run() == Gtk.ResponseType.YES:
            project_groups.remove_group(group_id, move_projects_to_default=True)
            self.refresh()
        dlg.destroy()


# ── Multi-Commit pinned command safety patch ────────────────────────────────
try:
    from gi.repository import Gtk
    from core import command_safety
except Exception:
    Gtk = None
    command_safety = None


def _mc_project_list_confirm_risky_command(self, command):
    if Gtk is None or command_safety is None:
        return True

    if not command_safety.is_dangerous(command):
        return True

    dlg = Gtk.MessageDialog(
        transient_for=self.get_toplevel(),
        flags=0,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.YES_NO,
        text="Risky pinned command detected"
    )
    dlg.format_secondary_text(command_safety.warning_text(command))
    response = dlg.run()
    dlg.destroy()
    return response == Gtk.ResponseType.YES


if not getattr(ProjectListPanel, "_mc_pinned_command_safety_patch_applied", False):
    ProjectListPanel._mc_base_run_pinned_command = getattr(ProjectListPanel, "_run_pinned_command", None)

    def _mc_safe_run_pinned_command(self, path, cmd):
        command = cmd.get("command", "") if isinstance(cmd, dict) else ""

        try:
            branch = get_current_branch(path) if is_git_repo(path) else ""
            command = project_commands.render(command, path, branch)
        except Exception:
            pass

        if command and not self._mc_project_list_confirm_risky_command(command):
            return

        if ProjectListPanel._mc_base_run_pinned_command:
            return ProjectListPanel._mc_base_run_pinned_command(self, path, cmd)

    ProjectListPanel._run_pinned_command = _mc_safe_run_pinned_command
    ProjectListPanel._mc_project_list_confirm_risky_command = _mc_project_list_confirm_risky_command
    ProjectListPanel._mc_pinned_command_safety_patch_applied = True


# ── Multi-Commit reset VSCode project action ────────────────────────────────
def _mc_reset_vscode(self, project_path):
    """
    Reset VSCode's remembered open editors/layout for this project.

    This moves matching VSCode workspaceStorage folders to a Multi-Commit
    backup folder, then opens the project folder in a new VSCode window.
    """
    project_name = os.path.basename(project_path.rstrip("/")) or project_path

    first = Gtk.MessageDialog(
        transient_for=self.get_toplevel(),
        flags=0,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Reset VSCode for {project_name}?"
    )
    first.format_secondary_text(
        "This clears VSCode's remembered open tabs/layout for this project only.\n\n"
        "It does NOT delete project files.\n"
        "It does NOT touch Git.\n\n"
        "Best result: close existing VSCode windows for this project first."
    )
    r1 = first.run()
    first.destroy()

    if r1 != Gtk.ResponseType.YES:
        return

    second = Gtk.MessageDialog(
        transient_for=self.get_toplevel(),
        flags=0,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.YES_NO,
        text="Are you absolutely sure?"
    )
    second.format_secondary_text(
        "Multi-Commit will move VSCode workspace/session state into a backup, "
        "then reopen this folder in a clean VSCode window."
    )
    r2 = second.run()
    second.destroy()

    if r2 != Gtk.ResponseType.YES:
        return

    try:
        result = vscode_reset.reset_project_workspace(project_path)
        opened = vscode_reset.open_clean_vscode(project_path)

        msg = (
            f"Matched VSCode workspace state folders: {result.get('matched', 0)}\n"
            f"Backup folder:\n{result.get('backup_root')}\n\n"
            f"VSCode opened: {'yes' if opened else 'no'}"
        )

        info = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="VSCode reset complete"
        )
        info.format_secondary_text(msg)
        info.run()
        info.destroy()

    except Exception as e:
        err = Gtk.MessageDialog(
            transient_for=self.get_toplevel(),
            flags=0,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="VSCode reset failed"
        )
        err.format_secondary_text(str(e))
        err.run()
        err.destroy()


if not getattr(ProjectListPanel, "_mc_reset_vscode_patch_applied", False):
    ProjectListPanel._reset_vscode = _mc_reset_vscode
    ProjectListPanel._mc_reset_vscode_patch_applied = True

