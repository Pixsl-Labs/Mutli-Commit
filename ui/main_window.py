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
from core import favourites
from ui.update_dialog import UpdatePromptWindow
from core import update_manager

ICON_PATH = os.path.join(os.path.dirname(__file__), "..", "assets", "icon.png")

class MainWindow(Gtk.Window):
    def __init__(self):
        super().__init__(title="Multi-Commit")
        self.set_wmclass("multi-commit", "Multi-Commit")
        self.set_default_size(960, 640)
        self.set_border_width(0)
        self._cmd_manager_win = None
        self._appearance_win  = None

        try:
            self.set_icon_from_file(os.path.abspath(ICON_PATH))
        except Exception:
            pass

        # Apply saved theme on startup
        apply_theme(load_theme())

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(vbox)
        vbox.pack_start(self._build_menubar(), False, False, 0)

        outer_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        outer_paned.set_position(320)
        vbox.pack_start(outer_paned, True, True, 0)

        self.commit_panel = CommitPanel()
        self.project_dashboard = ProjectDashboard(on_commands_changed=lambda: self.project_list.refresh())
        self.project_list = ProjectListPanel(
            on_select=self._on_project_selected,
            on_code_review=self._run_code_review,
        )

        right_paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        right_paned.set_position(300)
        right_paned.pack1(self.project_dashboard, resize=False, shrink=False)
        right_paned.pack2(self.commit_panel, resize=True, shrink=False)

        outer_paned.pack1(self.project_list, resize=False, shrink=False)
        outer_paned.pack2(right_paned, resize=True, shrink=False)

        self.statusbar = Gtk.Statusbar()
        self.statusbar.push(0, "Ready — select a project to begin")
        vbox.pack_end(self.statusbar, False, False, 0)

        GLib.timeout_add(1200, self._startup_update_check)

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

        # Spacer to push Settings + Help to the RIGHT
        spacer_item = Gtk.MenuItem(label="")
        spacer_item.set_sensitive(False)
        spacer_item.set_hexpand(True)  # GTK3 trick — won't visually push but groups nicely
        # We add Settings + Help last so they appear right of other items
        menubar.append(self._menu("Settings", [
            ("Preferences…",         self._open_settings),
            ("🎨 Appearance…",       self._open_appearance),
        ]))

        menubar.append(self._menu("Help", [
            ("Check for Updates",    self._manual_update_check),
            ("Preview Update Popup", self._preview_update_popup),
            None,
            ("Keyboard Shortcuts",   self._show_shortcuts),
            ("About Multi-Commit",   self._show_about),
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
            self.statusbar.push(0, f"✅ Code review saved: {out_path}")
            # Open the file in VSCode or xdg-open
            try:
                subprocess.Popen([s.get("vscode_cmd"), out_path])
            except Exception:
                subprocess.Popen(["xdg-open", out_path])
        except Exception as e:
            self.statusbar.push(0, f"❌ Code review failed: {e}")

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

    def _startup_update_check(self):
        info = update_manager.check_for_update()
        if info.get("available"):
            self._show_update_prompt(info)
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
            text="Multi-Commit is up to date"
        )
        dlg.format_secondary_text(info.get("message", "No update available."))
        dlg.run()
        dlg.destroy()

    def _preview_update_popup(self, _=None):
        info = update_manager.check_for_update(force_preview=True)
        self._show_update_prompt(info)

    def _show_update_prompt(self, info):
        popup = UpdatePromptWindow(self, info)
        popup.present_top_right()

    def _show_about(self, _=None):
        dlg = Gtk.AboutDialog()
        dlg.set_transient_for(self)
        dlg.set_program_name("Multi-Commit")
        dlg.set_version("1.0.0")
        dlg.set_comments("Git GUI for multiple remotes on Linux")
        dlg.set_website("https://github.com/Pixsl-Labs/Multi-Commit")
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