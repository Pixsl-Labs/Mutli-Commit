"""Update popup and progress dialog."""
import threading
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib
from core import update_manager


class UpdatePromptWindow(Gtk.Window):
    def __init__(self, parent, info):
        super().__init__(title="Multi-Commit Update")
        self.parent = parent
        self.info = info
        self.set_transient_for(parent)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_default_size(420, 150)
        self._apply_css()
        self._build()

    def _apply_css(self):
        css = b"""
        .update-popup {
            background: alpha(#1f2933, 0.96);
            border: 1px solid alpha(#3498db, 0.65);
            border-radius: 12px;
            padding: 12px;
        }
        .update-title {
            font-size: 14px;
            font-weight: bold;
            color: #d6ecff;
        }
        .update-body {
            font-size: 11px;
            color: alpha(#ffffff, 0.72);
        }
        .update-now-btn {
            background: alpha(#2ecc71, 0.22);
            color: #dfffe9;
            border: 1px solid alpha(#2ecc71, 0.45);
            border-radius: 6px;
            font-weight: bold;
        }
        .update-later-btn {
            background: alpha(#f1c40f, 0.16);
            color: #fff3c4;
            border: 1px solid alpha(#f1c40f, 0.35);
            border-radius: 6px;
        }
        .update-ignore-btn {
            background: alpha(#ffffff, 0.08);
            color: alpha(#ffffff, 0.75);
            border: 1px solid alpha(#ffffff, 0.18);
            border-radius: 6px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            __import__("gi.repository", fromlist=["Gdk"]).Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build(self):
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_border_width(12)
        outer.get_style_context().add_class("update-popup")
        self.add(outer)

        title = Gtk.Label(label="⬆ Multi-Commit update available")
        title.set_halign(Gtk.Align.START)
        title.get_style_context().add_class("update-title")
        outer.pack_start(title, False, False, 0)

        msg = self.info.get("message", "A new update is available.")
        branch = self.info.get("branch", "main")
        body = Gtk.Label(label=f"{msg}\nCurrent branch: {branch}")
        body.set_halign(Gtk.Align.START)
        body.set_line_wrap(True)
        body.get_style_context().add_class("update-body")
        outer.pack_start(body, False, False, 0)

        later_row = Gtk.Box(spacing=6)
        self.later_combo = Gtk.ComboBoxText()
        self.later_combo.append("3h", "In 3 hours")
        self.later_combo.append("online", "When PC comes back online")
        self.later_combo.append("close", "When app closes")
        self.later_combo.set_active_id("3h")
        later_row.pack_start(self.later_combo, True, True, 0)

        btn_row = Gtk.Box(spacing=6)

        update_btn = Gtk.Button(label="Update Now")
        update_btn.get_style_context().add_class("update-now-btn")
        update_btn.connect("clicked", self._update_now)
        btn_row.pack_start(update_btn, True, True, 0)

        later_btn = Gtk.Button(label="Update Later")
        later_btn.get_style_context().add_class("update-later-btn")
        later_btn.connect("clicked", self._update_later)
        btn_row.pack_start(later_btn, True, True, 0)

        ignore_btn = Gtk.Button(label="Close / Ignore")
        ignore_btn.get_style_context().add_class("update-ignore-btn")
        ignore_btn.connect("clicked", self._ignore)
        btn_row.pack_start(ignore_btn, True, True, 0)

        outer.pack_start(later_row, False, False, 0)
        outer.pack_start(btn_row, False, False, 0)

    def present_top_right(self):
        self.show_all()
        self.present()

        try:
            px, py = self.parent.get_position()
            pw, _ph = self.parent.get_size()
            self.move(px + max(20, pw - 450), py + 48)
        except Exception:
            self.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)

    def _update_now(self, _):
        self.destroy()
        dlg = UpdateProgressDialog(self.parent)
        dlg.show_all()
        dlg.start()

    def _update_later(self, _):
        mode = self.later_combo.get_active_id() or "3h"
        update_manager.defer_update(mode)
        self.destroy()

    def _ignore(self, _):
        update_manager.defer_update("ignore")
        self.destroy()


class UpdateProgressDialog(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="Updating Multi-Commit", transient_for=parent, flags=0)
        self.set_default_size(460, 170)
        self.add_button("Close", Gtk.ResponseType.CLOSE)
        self.close_btn = self.get_widget_for_response(Gtk.ResponseType.CLOSE)
        self.close_btn.set_sensitive(False)
        self.connect("response", self._on_response)
        self.success = False
        self._build()

    def _build(self):
        box = self.get_content_area()
        box.set_border_width(14)
        box.set_spacing(10)

        self.label = Gtk.Label(label="Starting update...")
        self.label.set_halign(Gtk.Align.START)
        box.pack_start(self.label, False, False, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.set_show_text(True)
        box.pack_start(self.progress, False, False, 0)

        self.output = Gtk.Label(label="")
        self.output.set_halign(Gtk.Align.START)
        self.output.set_line_wrap(True)
        box.pack_start(self.output, True, True, 0)

    def start(self):
        def run():
            ok, out = update_manager.apply_update(self._progress)
            GLib.idle_add(self._finished, ok, out)

        threading.Thread(target=run, daemon=True).start()

    def _progress(self, frac, msg):
        GLib.idle_add(self._set_progress, frac, msg)

    def _set_progress(self, frac, msg):
        self.progress.set_fraction(frac)
        self.progress.set_text(f"{int(frac * 100)}%")
        self.label.set_text(msg)
        return False

    def _finished(self, ok, out):
        self.success = ok
        self.progress.set_fraction(1.0 if ok else 0.0)
        self.progress.set_text("Complete" if ok else "Failed")
        self.label.set_text("✅ Update installed. Restarting..." if ok else "❌ Update failed")
        self.output.set_text(out[:500])
        self.close_btn.set_sensitive(True)

        if ok:
            GLib.timeout_add(1200, self._restart)

        return False

    def _restart(self):
        update_manager.restart_app()
        return False

    def _on_response(self, _dlg, _response):
        self.destroy()