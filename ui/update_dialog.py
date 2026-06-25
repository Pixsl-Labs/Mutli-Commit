"""Update UI for Multi-Commit."""
import threading
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

from core import update_manager, activity


class UpdatePromptWindow(Gtk.Window):
    def __init__(self, parent, info):
        super().__init__(title="Multi-Commit Update")
        self.parent = parent
        self.info = info or {}
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_default_size(390, 150)
        self._build()
        self.show_all()

    def _build(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        self.add(box)

        title = Gtk.Label()
        title.set_markup("<b>🔄 Multi-Commit update available</b>")
        title.set_halign(Gtk.Align.START)
        box.pack_start(title, False, False, 0)

        msg = Gtk.Label(label=self.info.get("message", "An update is available."))
        msg.set_halign(Gtk.Align.START)
        msg.set_line_wrap(True)
        box.pack_start(msg, False, False, 0)

        details = Gtk.Label(
            label=(
                f"Current: {self.info.get('current', 'unknown')}  →  "
                f"Latest: {self.info.get('latest', 'remote')}"
            )
        )
        details.set_halign(Gtk.Align.START)
        details.get_style_context().add_class("dim-label")
        box.pack_start(details, False, False, 0)

        row = Gtk.Box(spacing=6)
        box.pack_end(row, False, False, 0)

        update_btn = Gtk.Button(label="Update Now")
        update_btn.connect("clicked", self._update_now)
        row.pack_start(update_btn, False, False, 0)

        later_btn = Gtk.MenuButton(label="Update Later")
        later_menu = Gtk.Menu()
        for label, mode in [
            ("In 3 hours", "3h"),
            ("When online", "online"),
            ("When app closes", "close"),
            ("Ignore this update", "ignore"),
        ]:
            item = Gtk.MenuItem(label=label)
            item.connect("activate", self._defer, mode)
            later_menu.append(item)
        later_menu.show_all()
        later_btn.set_popup(later_menu)
        row.pack_start(later_btn, False, False, 0)

        center_btn = Gtk.Button(label="Update Center")
        center_btn.connect("clicked", self._open_center)
        row.pack_start(center_btn, False, False, 0)

        close_btn = Gtk.Button(label="Close")
        close_btn.connect("clicked", lambda _: self.destroy())
        row.pack_end(close_btn, False, False, 0)

    def present_top_right(self):
        self.show_all()
        try:
            screen = Gdk.Screen.get_default()
            monitor = screen.get_primary_monitor()
            geom = screen.get_monitor_geometry(monitor)
            self.move(geom.x + geom.width - 410, geom.y + 50)
        except Exception:
            self.set_position(Gtk.WindowPosition.CENTER)
        self.present()

    def _defer(self, _item, mode):
        update_manager.defer_update(mode)
        self.destroy()

    def _open_center(self, _=None):
        win = UpdateCenterWindow(self.parent)
        win.present()
        self.destroy()

    def _update_now(self, _=None):
        win = UpdateCenterWindow(self.parent)
        win.present()
        win.start_update()
        self.destroy()


class UpdateCenterWindow(Gtk.Window):
    def __init__(self, parent):
        super().__init__(title="🔄 Multi-Commit Update Center")
        self.parent = parent
        self.set_transient_for(parent)
        self.set_default_size(760, 520)
        self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        self._build()
        self.refresh_status()
        self.show_all()

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_border_width(10)
        self.add(root)

        header = Gtk.Label()
        header.set_markup("<b>🔄 Update Center</b>")
        header.set_halign(Gtk.Align.START)
        root.pack_start(header, False, False, 0)

        self.status_lbl = Gtk.Label(label="Checking status...")
        self.status_lbl.set_halign(Gtk.Align.START)
        self.status_lbl.set_line_wrap(True)
        root.pack_start(self.status_lbl, False, False, 0)

        btn_row = Gtk.Box(spacing=6)
        root.pack_start(btn_row, False, False, 0)

        check_btn = Gtk.Button(label="Check Now")
        check_btn.connect("clicked", lambda _: self.refresh_status())
        btn_row.pack_start(check_btn, False, False, 0)

        preview_btn = Gtk.Button(label="Preview Popup")
        preview_btn.set_tooltip_text("Shows the update popup even if no update exists.")
        preview_btn.connect("clicked", self._preview_popup)
        btn_row.pack_start(preview_btn, False, False, 0)

        update_btn = Gtk.Button(label="Update Now")
        update_btn.connect("clicked", lambda _: self.start_update())
        btn_row.pack_start(update_btn, False, False, 0)

        release_btn = Gtk.Button(label="Release Builder")
        release_btn.connect("clicked", self._open_release_builder)
        btn_row.pack_start(release_btn, False, False, 0)

        restart_btn = Gtk.Button(label="Restart App")
        restart_btn.connect("clicked", lambda _: update_manager.restart_app())
        btn_row.pack_end(restart_btn, False, False, 0)

        self.progress = Gtk.ProgressBar()
        root.pack_start(self.progress, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        self.output = Gtk.TextView()
        self.output.set_editable(False)
        self.output.set_monospace(True)
        self.output_buf = self.output.get_buffer()
        scroll.add(self.output)
        root.pack_start(scroll, True, True, 0)

    def _append(self, text):
        end = self.output_buf.get_end_iter()
        self.output_buf.insert(end, str(text).rstrip() + "\n")

    def _set_output(self, text):
        self.output_buf.set_text(text or "")

    def refresh_status(self):
        self.progress.set_fraction(0.25)
        self.status_lbl.set_text("Checking repository update status...")
        self._set_output("Checking update status...\n")

        def worker():
            summary = update_manager.repo_summary()
            info = update_manager.check_for_update()

            def done():
                self.progress.set_fraction(0.0)
                self.status_lbl.set_text(info.get("message", "Status checked."))

                lines = [
                    "=== Multi-Commit Update Status ===",
                    f"App version: {summary.get('version')}",
                    f"Branch: {summary.get('branch')}",
                    f"Upstream: {summary.get('upstream')}",
                    f"Dirty working tree: {summary.get('dirty')}",
                    f"Latest commit: {summary.get('latest_commit')}",
                    f"Local tag: {summary.get('local_tag') or 'none'}",
                    f"Remote/latest tag: {summary.get('remote_tag') or 'none'}",
                    "",
                    "=== Update Check ===",
                    f"Available: {info.get('available')}",
                    f"Message: {info.get('message')}",
                    f"Behind: {info.get('behind', 0)}",
                    f"Ahead: {info.get('ahead', 0)}",
                ]
                self._set_output("\n".join(lines))
                return False

            GLib.idle_add(done)

        threading.Thread(target=worker, daemon=True).start()

    def _preview_popup(self, _=None):
        info = update_manager.check_for_update(force_preview=True)
        popup = UpdatePromptWindow(self.parent, info)
        popup.present_top_right()

    def start_update(self):
        self.progress.set_fraction(0.15)
        self.status_lbl.set_text("Running safe update...")
        self._append("\nStarting update...")

        def worker():
            result = update_manager.apply_update()

            def done():
                self.progress.set_fraction(1.0 if result.get("ok") else 0.0)
                self._append(result.get("message", "Update finished."))

                try:
                    activity.log_event(
                        "",
                        "update_success" if result.get("ok") else "update_failed",
                        result.get("message", ""),
                    )
                except Exception:
                    pass

                if result.get("ok") and result.get("restart"):
                    self.status_lbl.set_text("✅ Updated. Restart Multi-Commit to use the new version.")
                    self._ask_restart()
                else:
                    self.status_lbl.set_text("❌ Update not applied.")
                return False

            GLib.idle_add(done)

        threading.Thread(target=worker, daemon=True).start()

    def _ask_restart(self):
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Restart Multi-Commit now?"
        )
        dlg.format_secondary_text("The update was applied successfully.")
        response = dlg.run()
        dlg.destroy()

        if response == Gtk.ResponseType.YES:
            update_manager.restart_app()

    def _open_release_builder(self, _=None):
        dlg = ReleaseBuilderDialog(self)
        dlg.run()
        dlg.destroy()


class ReleaseBuilderDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="🚀 Release Builder", transient_for=parent, flags=0)
        self.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Create Release", Gtk.ResponseType.OK)
        self.set_default_size(720, 520)
        self._build()
        self.show_all()

    def _build(self):
        box = self.get_content_area()
        box.set_border_width(10)
        box.set_spacing(8)

        self.version_entry = Gtk.Entry()
        self.version_entry.set_placeholder_text("v1.2.0")
        box.pack_start(Gtk.Label(label="Version tag:"), False, False, 0)
        box.pack_start(self.version_entry, False, False, 0)

        gen_btn = Gtk.Button(label="Generate Release Notes")
        gen_btn.connect("clicked", self._generate_notes)
        box.pack_start(gen_btn, False, False, 0)

        self.push_check = Gtk.CheckButton(label="Push tag to origin after creating")
        self.push_check.set_active(False)
        box.pack_start(self.push_check, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(300)
        self.notes_view = Gtk.TextView()
        self.notes_view.set_monospace(True)
        self.notes_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.notes_buf = self.notes_view.get_buffer()
        scroll.add(self.notes_view)
        box.pack_start(scroll, True, True, 0)

        self.result_lbl = Gtk.Label(label="")
        self.result_lbl.set_halign(Gtk.Align.START)
        self.result_lbl.set_line_wrap(True)
        box.pack_start(self.result_lbl, False, False, 0)

    def _generate_notes(self, _=None):
        version = self.version_entry.get_text().strip() or "v1.2.0"
        notes = update_manager.generate_release_notes(version)
        self.notes_buf.set_text(notes)

    def run(self):
        response = super().run()

        if response == Gtk.ResponseType.OK:
            version = self.version_entry.get_text().strip()
            start, end = self.notes_buf.get_bounds()
            notes = self.notes_buf.get_text(start, end, False)

            result = update_manager.create_release(
                version,
                notes,
                push=self.push_check.get_active(),
            )

            if result.get("ok"):
                try:
                    activity.log_event("", "release_created", result.get("message", "Release created"))
                except Exception:
                    pass

                info = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    text="Release created"
                )
                info.format_secondary_text(result.get("message", "Release created."))
                info.run()
                info.destroy()
            else:
                err = Gtk.MessageDialog(
                    transient_for=self,
                    flags=0,
                    message_type=Gtk.MessageType.ERROR,
                    buttons=Gtk.ButtonsType.OK,
                    text="Release failed"
                )
                err.format_secondary_text(result.get("message", "Could not create release."))
                err.run()
                err.destroy()
                return Gtk.ResponseType.CANCEL

        return response
