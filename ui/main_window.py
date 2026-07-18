"""Main GTK window — restructured menubar + all features wired up."""
import os
import subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib
from ui.project_list import ProjectListPanel
from ui.commit_panel import CommitPanel
from ui.project_dashboard import ProjectDashboard
from ui.settings_dialog import SettingsDialog
from ui.command_manager import CommandManagerWindow
from ui.appearance_dialog import AppearanceDialog, apply_theme, load_theme
from ui.checklist_window import ChecklistWindow
from core import favourites, config_backup, settings
from ui.update_dialog import UpdatePromptWindow, UpdateCenterWindow
from core import update_manager, activity
from ui.code_review_manager import CodeReviewManagerWindow
from ui.table_lab import TableLabWindow

from ui.diagnostics_window import DiagnosticsWindow

from ui.handoff_generator import HandoffGeneratorWindow

from core import command_safety

from ui.focus_window import FocusWindow

from ui.project_templates_window import ProjectTemplatesWindow

ICON_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png")

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="DevWise")
        self.set_wmclass("devwise", "DevWise")
        self.set_default_size(960, 640)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_border_width(0)
        self._cmd_manager_win = None
        self._appearance_win  = None
        self._code_review_manager_win = None
        self._table_lab_win = None
        self._update_prompt_win = None
        self._last_update_popup_id = None

        try:
            self.set_icon_from_file(os.path.abspath(ICON_PATH))
        except Exception:
            pass

        # Apply saved theme on startup
        apply_theme(load_theme())

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)
        vbox.pack_start(self._build_menubar(), False, False, 0)

        # Main layout:
        # Sidebar | Project Dashboard | Git/Tools Panel
        # Both splitters are draggable and their positions are remembered.
        self.outer_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.outer_paned.set_position(int(settings.get("main_outer_pane_position") or 340))
        try:
            self.outer_paned.set_wide_handle(True)
        except Exception:
            pass
        vbox.pack_start(self.outer_paned, True, True, 0)

        self.commit_panel = CommitPanel()
        self.project_dashboard = ProjectDashboard(on_commands_changed=lambda: self.project_list.refresh())
        self.project_list = ProjectListPanel(
            on_select=self._on_project_selected,
            on_code_review=self._run_code_review,
        )

        self.right_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        self.right_paned.set_position(int(settings.get("main_right_pane_position") or 330))
        try:
            self.right_paned.set_wide_handle(True)
        except Exception:
            pass

        # resize=True means all three areas can be pulled/resized properly.
        self.right_paned.pack1(self.project_dashboard, resize=True, shrink=False)
        self.right_paned.pack2(self.commit_panel, resize=True, shrink=False)

        self.outer_paned.pack1(self.project_list, resize=True, shrink=False)
        self.outer_paned.pack2(self.right_paned, resize=True, shrink=False)

        self.outer_paned.connect("notify::position", self._save_main_pane_positions)
        self.right_paned.connect("notify::position", self._save_main_pane_positions)

        self.statusbar = Gtk.Statusbar()
        self.statusbar.push(0, "Ready — select a project to begin")
        vbox.pack_end(self.statusbar, False, False, 0)

        self.connect("delete-event", self._on_main_delete_event)

        GLib.timeout_add(1200, self._startup_update_check)
        GLib.timeout_add_seconds(10, self._realtime_update_check)

    def _save_main_pane_positions(self, *_):
        """Remember main splitter positions between launches."""
        try:
            if hasattr(self, "outer_paned"):
                settings.set_value("main_outer_pane_position", int(self.outer_paned.get_position()))
            if hasattr(self, "right_paned"):
                settings.set_value("main_right_pane_position", int(self.right_paned.get_position()))
        except Exception:
            pass

    # ── Menubar ──────────────────────────────────────────────────────────────

    def _build_menubar(self):
        menubar = Gtk.MenuBar()

        # LEFT side — primary actions
        menubar.append(self._menu("File", [
            ("Open Project Folder",  lambda _: self.project_list.open_folder_dialog()),
            None,
            ("Quit  Ctrl+Q",         lambda _: Gtk.main_quit()),
        ]))

        menubar.append(self._menu("⚡ Commands", [
            ("Command Manager…",     self._open_command_manager),
            None,
            *self._fav_menu_items(),
        ]))

        menubar.append(self._menu("Git", [
            ("Pull current branch",  lambda _: self._git_action("git pull")),
            ("Fetch all",            lambda _: self._git_action("git fetch --all")),
            ("Git status",           lambda _: self._git_action("git status")),
            None,
            ("Generate Code Review", self._run_code_review),
            ("✅ Open Checklist",     self._open_checklist),
        ]))

        menubar.append(self._menu("Code Reviews", [
            ("Open Code Review Manager", self._open_code_review_manager),
        ]))

        menubar.append(self._menu("Tools", [
            ("🧪 Table Lab", self._open_table_lab),
        ]))

        # Spacer to push Settings + Help to the RIGHT
        spacer_item = Gtk.MenuItem(label="")
        spacer_item.set_sensitive(False)
        spacer_item.set_hexpand(True)  # GTK3 trick — won't visually push but groups nicely
        # We add Settings + Help last so they appear right of other items
        menubar.append(self._menu("Settings", [
            ("Preferences…",          self._open_settings),
            ("🎨 Appearance…",        self._open_appearance),
            None,
            ("Export Config Backup",  self._export_config_backup),
            ("Restore Config Backup", self._restore_config_backup),
        ]))

        menubar.append(self._menu("Help", [
            ("Check for Updates",    self._manual_update_check),
            ("Preview Update Popup", self._preview_update_popup),
            ("🧪 Create Test Update", self._create_test_update_popup),
            ("Clear Test Update", self._clear_test_update),
            None,
            ("Keyboard Shortcuts",   self._show_shortcuts),
            ("About DevWise",   self._show_about),
        ]))

        menubar.append(self._menu("Updates", [
            ("🔄 Update Center", self._open_update_center),
            ("Check for Updates", self._manual_update_check),
            ("Preview Update Popup", self._preview_update_popup),
        ]))

        return menubar

    def _menu(self, label, items):
        """Helper: build a Gtk.MenuItem with submenu from a list of (label, cb) or None for separator."""
        menu = Gtk.Menu()
        item = Gtk.MenuItem(label=label)
        item.set_submenu(menu)
        for entry in items:
            if entry is None:
                menu.append(Gtk.SeparatorMenuItem())
            elif isinstance(entry, tuple):
                lbl, cb = entry
                mi = Gtk.MenuItem(label=lbl)
                mi.connect("activate", cb)
                menu.append(mi)
            else:
                # Raw menu item passed directly
                menu.append(entry)
        return item

    def _fav_menu_items(self):
        """Return flat list of menu items for favourites grouped by category."""
        items = []
        favs = favourites.load()
        cats = {}
        for i, fav in enumerate(favs):
            cats.setdefault(fav.get("category", "General"), []).append((i, fav))

        for cat, fav_list in sorted(cats.items()):
            sep_item = Gtk.MenuItem(label=f"  {cat}")
            sep_item.set_sensitive(False)
            items.append(sep_item)
            for i, fav in fav_list:
                mi = Gtk.MenuItem(label=f"    ▶ {fav['name']}")
                mi.connect("activate", self._quick_run_fav, i)
                items.append(mi)
        return items

    def _quick_run_fav(self, _, index):
        from core.git_ops import run_custom
        from core import settings as s
        fav = favourites.load()[index]
        cwd = self.commit_panel.project_path or os.path.expanduser("~")
        if fav.get("use_terminal"):
            bash_cmd = f"{fav['command']}; echo; echo '--- Done. Press Enter to close ---'; read"
            term = s.get("terminal_cmd")
            for t in [term, "kitty", "x-terminal-emulator", "gnome-terminal", "xterm"]:
                try:
                    subprocess.Popen([t, "--", "bash", "-c", bash_cmd], cwd=cwd)
                    self.statusbar.push(0, f"🖥 Terminal: {fav['name']}")
                    return
                except FileNotFoundError:
                    continue
        else:
            ok, out = run_custom(cwd, fav["command"])
            self.statusbar.push(0, f"{'✅' if ok else '❌'} {fav['name']}: {out[:80]}")

    def _git_action(self, cmd, _=None):
        path = self.commit_panel.project_path
        if not path:
            self.statusbar.push(0, "❌ No project selected")
            return
        from core.git_ops import run_custom
        ok, out = run_custom(path, cmd)
        self.statusbar.push(0, f"{'✅' if ok else '❌'} {cmd}: {out[:80]}")
        self.commit_panel._log(f"$ {cmd}\n{out}")

    # ── Window launchers ─────────────────────────────────────────────────────

    def _on_project_selected(self, path):
        self.commit_panel.set_project(path)
        self.project_dashboard.set_project(path)
        self.statusbar.push(0, f"Project: {path}")

    def _open_command_manager(self, _=None):
        if self._cmd_manager_win and self._cmd_manager_win.get_visible():
            self._cmd_manager_win.present()
            return
        self._cmd_manager_win = CommandManagerWindow(
            self, project_path=self.commit_panel.project_path
        )

    def _open_appearance(self, _=None):
        if self._appearance_win and self._appearance_win.get_visible():
            self._appearance_win.present()
            return
        self._appearance_win = AppearanceDialog(self)

    def _open_settings(self, _=None):
        dlg = SettingsDialog(self, project_path=self.commit_panel.project_path)
        dlg.run()
        dlg.destroy()

    def _run_code_review(self, path=None, _=None):
        target = path or self.commit_panel.project_path
        if not target:
            self.statusbar.push(0, "❌ No project selected for code review")
            return
        from core.code_review import generate
        from core import settings as s
        output_dir = os.path.expanduser(s.get("code_review_output_dir") or "~/Projects/Code Reviews")
        os.makedirs(output_dir, exist_ok=True)
        try:
            out_path = generate(target, output_dir)
            activity.log_event(target, "code_review_generated", f"Generated code review: {out_path}")
            self.statusbar.push(0, f"✅ Code review saved: {out_path}")
            # Open the file in VSCode or xdg-open
            try:
                subprocess.Popen([s.get("vscode_cmd"), out_path])
            except Exception:
                subprocess.Popen(["xdg-open", out_path])
        except Exception as e:
            self.statusbar.push(0, f"❌ Code review failed: {e}")

    def _open_code_review_manager(self, _=None):
        if self._code_review_manager_win and self._code_review_manager_win.get_visible():
            self._code_review_manager_win.present()
            return

        self._code_review_manager_win = CodeReviewManagerWindow(self)

    def _table_lab_is_open(self):
        return getattr(self, "_table_lab_win", None) is not None


    def _on_main_delete_event(self, _window, _event):
        """
        Let Table Lab survive when the main window is closed.

        If Table Lab exists, hide the main window instead of destroying it.
        If Table Lab is not open, allow the normal close/quit behaviour.
        """
        if self._table_lab_is_open():
            self.hide()

            try:
                self._table_lab_win.present()
            except Exception:
                pass

            return True

        return False


    def _on_table_lab_destroy(self, *_):
        self._table_lab_win = None

        # If the user closed the main window while using Table Lab,
        # bring the main window back when Table Lab closes.
        if not self.get_visible():
            self.show()
            self.present()


    def _open_table_lab(self, _=None):
        if self._table_lab_win is not None and self._table_lab_win.get_visible():
            self._table_lab_win.present()
            return

        self._table_lab_win = TableLabWindow(self)
        self._table_lab_win.connect("destroy", self._on_table_lab_destroy)
        self._table_lab_win.show_all()


    # ── Help dialogs ─────────────────────────────────────────────────────────

    def _show_shortcuts(self, _=None):
        dlg = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Keyboard Shortcuts"
        )
        dlg.format_secondary_markup(
            "<b>Ctrl+Enter</b>  —  Quick Commit (add → commit → push all)\n"
            "<b>Enter</b>       —  Confirm current step\n"
            "<b>Ctrl+Q</b>      —  Quit\n"
        )
        dlg.run()
        dlg.destroy()

    def _open_update_center(self, _=None):
        win = UpdateCenterWindow(self)
        win.present()

    def _realtime_update_check(self):
        """
        Lightweight live watcher.

        Only checks the local test update file so the popup can appear while
        the app is open. It does NOT run git fetch / remote update checks.
        """
        try:
            if not hasattr(update_manager, "live_update_info"):
                return True

            info = update_manager.live_update_info()

            if not info or not info.get("available"):
                return True

            update_id = info.get("id") or f"{info.get('latest', 'test')}-{info.get('behind', 0)}"

            if update_id == getattr(self, "_last_update_popup_id", None):
                return True

            self._last_update_popup_id = update_id
            self._show_update_prompt(info)

            try:
                self.statusbar.push(0, "🔄 Test update available: " + info.get("message", ""))
            except Exception:
                pass

        except Exception as e:
            try:
                self.statusbar.push(0, f"Live update watcher skipped: {e}")
            except Exception:
                pass

        return True

    def _create_test_update_popup(self, _=None):
        info = update_manager.create_test_update(
            "Live test update created — this popup appeared while the app was open."
        )
        self._last_update_popup_id = None
        self._show_update_prompt(info)

        try:
            self.statusbar.push(0, "🧪 Test update created.")
        except Exception:
            pass


    def _clear_test_update(self, _=None):
        update_manager.clear_test_update()
        self._last_update_popup_id = None

        try:
            self.statusbar.push(0, "Test update cleared.")
        except Exception:
            pass

    def _startup_update_check(self):
        """
        Startup check is now cheap.

        Do not run remote git fetch automatically on app open because it can
        freeze/lag the GTK UI. Manual update checks still do the full check.
        """
        try:
            info = None

            if hasattr(update_manager, "live_update_info"):
                info = update_manager.live_update_info()

            if info and info.get("available"):
                self._show_update_prompt(info)

        except Exception as e:
            try:
                self.statusbar.push(0, f"Startup update check skipped: {e}")
            except Exception:
                pass

        return False

    def _manual_update_check(self, _=None):
        info = update_manager.check_for_update()
        if info.get("available"):
            self._show_update_prompt(info)
            return

        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="DevWise is up to date"
        )
        dlg.format_secondary_text(info.get("message", "No update available."))
        dlg.run()
        dlg.destroy()

    def _preview_update_popup(self, _=None):
        info = update_manager.check_for_update(force_preview=True)
        self._show_update_prompt(info)

    def _show_update_prompt(self, info):
        try:
            if self._update_prompt_win is not None and self._update_prompt_win.get_visible():
                self._update_prompt_win.present_top_right()
                return
        except Exception:
            self._update_prompt_win = None

        popup = UpdatePromptWindow(self, info)
        self._update_prompt_win = popup
        popup.connect("destroy", lambda *_: setattr(self, "_update_prompt_win", None))
        popup.present_top_right()

    def _show_about(self, _=None):
        dlg = Gtk.AboutDialog()
        dlg.set_transient_for(self)
        dlg.set_program_name("DevWise")
        dlg.set_version("1.0.0")
        dlg.set_comments("Git GUI for multiple remotes on Linux")
        dlg.set_website("https://github.com/Pixsl-Labs/DevWise")
        dlg.set_authors(["Sam (Pixsl-Labs)"])
        try:
            dlg.set_logo(GdkPixbuf.Pixbuf.new_from_file_at_size(
                os.path.abspath(ICON_PATH), 64, 64))
        except Exception:
            pass
        dlg.run()
        dlg.destroy()

    def _open_checklist(self, _=None):
        path = self.commit_panel.project_path
        if not path:
            self.statusbar.push(0, "❌ No project selected for checklist")
            return
        win = ChecklistWindow(self, path)
        win.show_all()

    def _export_config_backup(self, _=None):
        dlg = Gtk.FileChooserDialog(
            title="Export DevWise Config Backup",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                    Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        )
        dlg.set_do_overwrite_confirmation(True)
        dlg.set_current_folder(os.path.expanduser("~/Projects"))
        dlg.set_current_name("devwise-backup.zip")

        if dlg.run() == Gtk.ResponseType.OK:
            try:
                out_path = config_backup.export_backup(dlg.get_filename())
                activity.log_event("", "config_backup_exported", f"Exported config backup: {out_path}")
                self.statusbar.push(0, f"✅ Config backup exported: {out_path}")
            except Exception as e:
                self.statusbar.push(0, f"❌ Backup failed: {e}")

        dlg.destroy()

    def _restore_config_backup(self, _=None):
        dlg = Gtk.FileChooserDialog(
            title="Restore DevWise Config Backup",
            transient_for=self,
            action=Gtk.FileChooserAction.OPEN,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                    Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        )

        file_filter = Gtk.FileFilter()
        file_filter.set_name("Zip backups")
        file_filter.add_pattern("*.zip")
        dlg.add_filter(file_filter)

        if dlg.run() != Gtk.ResponseType.OK:
            dlg.destroy()
            return

        zip_path = dlg.get_filename()
        dlg.destroy()

        confirm = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Restore config backup?"
        )
        confirm.format_secondary_text(
            "This will overwrite current DevWise settings, projects, commands, checklists and notes.\n\n"
            "Restart DevWise after restoring."
        )

        response = confirm.run()
        confirm.destroy()

        if response != Gtk.ResponseType.YES:
            return

        try:
            restored = config_backup.restore_backup(zip_path)
            activity.log_event("", "config_backup_restored", f"Restored config backup: {zip_path}")
            self.statusbar.push(0, f"✅ Restored backup: {', '.join(restored)}")
        except Exception as e:
            self.statusbar.push(0, f"❌ Restore failed: {e}")


# ── DevWise power tools menu patch ─────────────────────────────────────
def _mc_current_project_path(self):
    try:
        return self.commit_panel.project_path
    except Exception:
        return None


def _mc_open_diagnostics(self, _=None):
    win = DiagnosticsWindow(self, self._mc_current_project_path())
    win.present()


def _mc_open_handoff_generator(self, _=None):
    path = self._mc_current_project_path()

    if not path:
        try:
            self.statusbar.push(0, "❌ Select a project before opening Handoff Generator.")
        except Exception:
            pass
        return

    win = HandoffGeneratorWindow(self, path)
    win.present()


def _mc_show_command_safety_guide(self, _=None):
    dlg = Gtk.MessageDialog(
        transient_for=self,
        flags=0,
        message_type=Gtk.MessageType.INFO,
        buttons=Gtk.ButtonsType.OK,
        text="Command Safety Guardrails"
    )
    dlg.format_secondary_text(command_safety.safety_guide())
    dlg.run()
    dlg.destroy()


def _mc_power_menu_item(label, callback):
    item = Gtk.MenuItem(label=label)
    item.connect("activate", callback)
    return item


if not getattr(MainWindow, "_mc_power_tools_patch_applied", False):
    MainWindow._mc_base_build_menubar = MainWindow._build_menubar

    def _mc_build_menubar(self):
        menubar = MainWindow._mc_base_build_menubar(self)

        menu = Gtk.Menu()
        root = Gtk.MenuItem(label="Power Tools")
        root.set_submenu(menu)

        menu.append(_mc_power_menu_item("🩺 Diagnostics / Compile Check", self._mc_open_diagnostics))
        menu.append(_mc_power_menu_item("📘 Handoff Generator", self._mc_open_handoff_generator))
        menu.append(_mc_power_menu_item("🛡 Command Safety Guide", self._mc_show_command_safety_guide))

        try:
            menu.append(Gtk.SeparatorMenuItem())
            menu.append(_mc_power_menu_item("🧪 Create Live Test Update", self._create_test_update_popup))
            menu.append(_mc_power_menu_item("Clear Test Update", self._clear_test_update))
        except Exception:
            pass

        menu.show_all()
        menubar.append(root)
        return menubar

    MainWindow._build_menubar = _mc_build_menubar
    MainWindow._mc_current_project_path = _mc_current_project_path
    MainWindow._mc_open_diagnostics = _mc_open_diagnostics
    MainWindow._mc_open_handoff_generator = _mc_open_handoff_generator
    MainWindow._mc_show_command_safety_guide = _mc_show_command_safety_guide
    MainWindow._mc_power_tools_patch_applied = True


# ── DevWise workflow menu patch ─────────────────────────────────────────────
def _dw_current_project_path(self):
    try:
        return self.commit_panel.project_path
    except Exception:
        return None


def _dw_open_focus_mode(self, _=None):
    path = self._dw_current_project_path()
    win = FocusWindow(self, path)
    win.present()


def _dw_open_project_templates(self, _=None):
    path = self._dw_current_project_path()
    win = ProjectTemplatesWindow(self, path)
    win.present()


if not getattr(MainWindow, "_dw_workflow_menu_patch_applied", False):
    MainWindow._dw_base_build_menubar = MainWindow._build_menubar

    def _dw_build_menubar(self):
        menubar = MainWindow._dw_base_build_menubar(self)

        menu = Gtk.Menu()
        root = Gtk.MenuItem(label="Workflows")
        root.set_submenu(menu)

        focus = Gtk.MenuItem(label="🎯 Focus Mode")
        focus.connect("activate", self._dw_open_focus_mode)
        menu.append(focus)

        templates = Gtk.MenuItem(label="🧩 Project Templates")
        templates.connect("activate", self._dw_open_project_templates)
        menu.append(templates)

        menu.show_all()
        menubar.append(root)
        return menubar

    MainWindow._build_menubar = _dw_build_menubar
    MainWindow._dw_current_project_path = _dw_current_project_path
    MainWindow._dw_open_focus_mode = _dw_open_focus_mode
    MainWindow._dw_open_project_templates = _dw_open_project_templates
    MainWindow._dw_workflow_menu_patch_applied = True

