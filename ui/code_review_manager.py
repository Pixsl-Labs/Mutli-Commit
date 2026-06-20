"""Code Review Manager window."""
import os
import subprocess
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, Gdk

from core import settings, activity


class CodeReviewManagerWindow(Gtk.Window):
    def __init__(self, parent):
        super().__init__(title="📋 Code Review Manager")
        self.set_transient_for(parent)
        self.set_default_size(820, 560)
        self.selected_path = None
        self._build()
        self.refresh()
        self.show_all()

    def _folders(self):
        folders = settings.get("code_review_folders") or []
        output_dir = settings.get("code_review_output_dir") or "~/Projects/Code Reviews"

        if output_dir not in folders:
            folders.insert(0, output_dir)

        result = []
        for folder in folders:
            expanded = os.path.abspath(os.path.expanduser(folder))
            if expanded not in result:
                result.append(expanded)

        return result

    def _save_folders(self, folders):
        settings.set_value("code_review_folders", folders)

    def _build(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        toolbar = Gtk.Box(spacing=6)
        toolbar.set_border_width(8)

        refresh_btn = Gtk.Button(label="↻ Refresh")
        refresh_btn.connect("clicked", lambda _: self.refresh())
        toolbar.pack_start(refresh_btn, False, False, 0)

        add_folder_btn = Gtk.Button(label="＋ Add Review Folder")
        add_folder_btn.connect("clicked", self._add_folder)
        toolbar.pack_start(add_folder_btn, False, False, 0)

        remove_folder_btn = Gtk.Button(label="－ Remove Folder")
        remove_folder_btn.connect("clicked", self._remove_folder)
        toolbar.pack_start(remove_folder_btn, False, False, 0)

        self.folder_combo = Gtk.ComboBoxText()
        self.folder_combo.connect("changed", lambda _: self.refresh())
        toolbar.pack_end(self.folder_combo, False, False, 0)

        vbox.pack_start(toolbar, False, False, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(340)
        vbox.pack_start(paned, True, True, 0)

        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-selected", self._on_select)

        scroll = Gtk.ScrolledWindow()
        scroll.add(self.list_box)
        paned.pack1(scroll, resize=False, shrink=False)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_border_width(12)

        self.title_lbl = Gtk.Label()
        self.title_lbl.set_markup("<b>Select a code review</b>")
        self.title_lbl.set_halign(Gtk.Align.START)
        self.title_lbl.set_line_wrap(True)
        right.pack_start(self.title_lbl, False, False, 0)

        self.path_lbl = Gtk.Label(label="")
        self.path_lbl.set_halign(Gtk.Align.START)
        self.path_lbl.set_line_wrap(True)
        self.path_lbl.get_style_context().add_class("dim-label")
        right.pack_start(self.path_lbl, False, False, 0)

        btn_grid = Gtk.Grid(column_spacing=8, row_spacing=8)

        actions = [
            ("Open in VSCode", self._open_vscode),
            ("Reveal in Folder", self._reveal_folder),
            ("Copy Path", self._copy_path),
            ("Delete Review", self._delete_review),
        ]

        for i, (label, cb) in enumerate(actions):
            btn = Gtk.Button(label=label)
            btn.connect("clicked", cb)
            btn_grid.attach(btn, i % 2, i // 2, 1, 1)

        right.pack_start(btn_grid, False, False, 0)

        preview_lbl = Gtk.Label()
        preview_lbl.set_markup("<b>Preview</b>")
        preview_lbl.set_halign(Gtk.Align.START)
        right.pack_start(preview_lbl, False, False, 0)

        preview_scroll = Gtk.ScrolledWindow()
        self.preview_buf = Gtk.TextBuffer()
        self.preview_view = Gtk.TextView(buffer=self.preview_buf)
        self.preview_view.set_editable(False)
        self.preview_view.set_monospace(True)
        self.preview_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        preview_scroll.add(self.preview_view)
        right.pack_start(preview_scroll, True, True, 0)

        paned.pack2(right, resize=True, shrink=False)

    def refresh(self):
        current_id = self.folder_combo.get_active_id()

        self.folder_combo.handler_block_by_func(lambda _: self.refresh())
        self.folder_combo.remove_all()
        for folder in self._folders():
            self.folder_combo.append(folder, folder)
        self.folder_combo.set_active_id(current_id or (self._folders()[0] if self._folders() else None))
        self.folder_combo.handler_unblock_by_func(lambda _: self.refresh())

        for child in self.list_box.get_children():
            self.list_box.remove(child)

        folder = self.folder_combo.get_active_id()
        if not folder or not os.path.isdir(folder):
            self.list_box.show_all()
            return

        files = []
        for root, _dirs, names in os.walk(folder):
            for name in names:
                if name.endswith(".md"):
                    full = os.path.join(root, name)
                    files.append(full)

        files.sort(key=lambda p: os.path.getmtime(p), reverse=True)

        for path in files:
            row = Gtk.ListBoxRow()
            row.path = path

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_border_width(8)

            name_lbl = Gtk.Label(label=os.path.basename(path))
            name_lbl.set_halign(Gtk.Align.START)
            name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            box.pack_start(name_lbl, False, False, 0)

            path_lbl = Gtk.Label(label=path)
            path_lbl.set_halign(Gtk.Align.START)
            path_lbl.set_ellipsize(Pango.EllipsizeMode.START)
            path_lbl.get_style_context().add_class("dim-label")
            box.pack_start(path_lbl, False, False, 0)

            row.add(box)
            self.list_box.add(row)

        self.list_box.show_all()

    def _on_select(self, _listbox, row):
        if not row or not hasattr(row, "path"):
            self.selected_path = None
            return

        self.selected_path = row.path
        self.title_lbl.set_markup(f"<b>{os.path.basename(row.path)}</b>")
        self.path_lbl.set_text(row.path)

        try:
            with open(row.path, "r", encoding="utf-8") as f:
                content = f.read(4000)
            self.preview_buf.set_text(content)
        except Exception as e:
            self.preview_buf.set_text(f"Could not read file: {e}")

    def _open_vscode(self, _=None):
        if not self.selected_path:
            return
        try:
            subprocess.Popen([settings.get("vscode_cmd") or "code", self.selected_path])
        except Exception:
            subprocess.Popen(["xdg-open", self.selected_path])

    def _reveal_folder(self, _=None):
        if not self.selected_path:
            return
        subprocess.Popen(["xdg-open", os.path.dirname(self.selected_path)])

    def _copy_path(self, _=None):
        if not self.selected_path:
            return
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(self.selected_path, -1)

    def _delete_review(self, _=None):
        if not self.selected_path:
            return

        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete {os.path.basename(self.selected_path)}?"
        )
        response = dlg.run()
        dlg.destroy()

        if response == Gtk.ResponseType.YES:
            try:
                os.remove(self.selected_path)
                activity.log_event("", "code_review_deleted", f"Deleted code review: {self.selected_path}")
                self.selected_path = None
                self.preview_buf.set_text("")
                self.refresh()
            except Exception as e:
                self._info(f"Could not delete file:\n{e}", "Error")

    def _add_folder(self, _=None):
        dlg = Gtk.FileChooserDialog(
            title="Add Code Review Folder",
            transient_for=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                     Gtk.STOCK_OPEN, Gtk.ResponseType.OK)
        )

        if dlg.run() == Gtk.ResponseType.OK:
            folder = dlg.get_filename()
            folders = self._folders()
            if folder not in folders:
                folders.append(folder)
                self._save_folders(folders)
                self.refresh()

        dlg.destroy()

    def _remove_folder(self, _=None):
        folder = self.folder_combo.get_active_id()
        if not folder:
            return

        folders = [f for f in self._folders() if os.path.abspath(os.path.expanduser(f)) != folder]
        self._save_folders(folders)
        self.refresh()

    def _info(self, message, title="Info"):
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )
        dlg.format_secondary_text(message)
        dlg.run()
        dlg.destroy()