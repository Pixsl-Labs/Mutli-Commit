"""Project Checklist / Roadmap window — standalone Gtk.Window per project."""
import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, Gdk, GLib

from core import checklists, activity, settings


class ChecklistWindow(Gtk.Window):
    def __init__(self, parent, project_path):
        """Standalone checklist/roadmap window for a single project."""
        super().__init__(title="✅ Checklist — " + os.path.basename(project_path))
        self.parent_window = parent
        # Not transient — so this window survives hiding/minimizing the main window
        self.set_default_size(640, 480)
        self.set_size_request(260, 200)
        self._restore_window_geometry()
        self.project_path = os.path.abspath(os.path.expanduser(project_path))
        self.project_data = checklists.get_project_data(project_path)

        # Make sure structure is sane even if file was empty/corrupt
        if "stages" not in self.project_data:
            self.project_data["stages"] = []

        self.selected_stage_index = None
        self.selected_item_index = None
        self._dirty = False
        self._autosave_timeout = None
        self._autosave_enabled = bool(self.project_data.get("autosave", True))

        self._apply_css()
        self._build()
        self._refresh_stage_list()
        self._update_save_button_style()
        self.connect("delete-event", self._on_close)
        self.show_all()

    # ── Styling ──────────────────────────────────────────────────────────────

    def _apply_css(self):
        css = b"""
        .checklist-toolbar {
            background: alpha(white, 0.03);
            border-bottom: 1px solid alpha(white, 0.08);
            padding: 8px;
        }
        .stage-row { border-bottom: 1px solid alpha(white, 0.07); }
        .stage-row:selected { background: alpha(white, 0.10); }
        .stage-title { font-size: 13px; font-weight: bold; }
        .stage-progress { font-size: 10px; opacity: 0.6; }
        .item-row { border-bottom: 1px solid alpha(white, 0.05); }
        .item-text-done {
            text-decoration: line-through;
            opacity: 0.5;
        }
        .progress-label { font-size: 12px; font-weight: bold; }
        .notes-view {
            font-family: sans-serif; font-size: 12px;
            background: alpha(#3498db, 0.05);
        }
        .item-description {
            font-size: 11px;
            opacity: 0.72;
            background: alpha(#3498db, 0.06);
            border-left: 2px solid alpha(#3498db, 0.35);
            padding: 6px;
            margin-left: 26px;
        }
        .save-btn-saved {
            background: #27ae60; color: white;
            border-radius: 4px;
        }
        .save-btn-unsaved {
            background: #e67e22; color: white;
            border-radius: 4px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            __import__("gi.repository", fromlist=["Gdk"]).Gdk.Screen.get_default(),
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build(self):
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(vbox)

        # ── Top toolbar ──
        toolbar = Gtk.Box(spacing=8)
        toolbar.get_style_context().add_class("checklist-toolbar")

        toolbar_scroll = Gtk.ScrolledWindow()
        toolbar_scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        toolbar_scroll.set_propagate_natural_height(True)
        toolbar_scroll.add(toolbar)

        import_btn = Gtk.Button(label="📋 Paste / Import Roadmap")
        import_btn.connect("clicked", self._open_import_dialog)
        toolbar.pack_start(import_btn, False, False, 0)

        add_stage_btn = Gtk.Button(label="➕ Add Stage")
        add_stage_btn.connect("clicked", self._add_stage)
        toolbar.pack_start(add_stage_btn, False, False, 0)

        add_item_btn = Gtk.Button(label="➕ Add Item")
        add_item_btn.connect("clicked", self._add_item)
        toolbar.pack_start(add_item_btn, False, False, 0)

        export_btn = Gtk.Button(label="📤 Export")
        export_btn.connect("clicked", self._export_checklist)
        toolbar.pack_start(export_btn, False, False, 0)

        delete_all_btn = Gtk.Button(label="🗑 Delete All")
        delete_all_btn.connect("clicked", self._delete_all_checklist)
        toolbar.pack_start(delete_all_btn, False, False, 0)

        save_btn = Gtk.Button(label="💾 Save")
        save_btn.connect("clicked", lambda _: self._save())
        toolbar.pack_end(save_btn, False, False, 0)
        self.save_btn = save_btn

        autosave_box = Gtk.Box(spacing=4)
        autosave_lbl = Gtk.Label(label="Auto-save")
        self.autosave_switch = Gtk.Switch()
        self.autosave_switch.set_active(self._autosave_enabled)
        self.autosave_switch.connect("notify::active", self._on_autosave_toggled)
        autosave_box.pack_start(autosave_lbl, False, False, 0)
        autosave_box.pack_start(self.autosave_switch, False, False, 0)
        toolbar.pack_end(autosave_box, False, False, 8)

        self.overall_progress_lbl = Gtk.Label(label="")
        self.overall_progress_lbl.get_style_context().add_class("progress-label")
        toolbar.pack_end(self.overall_progress_lbl, False, False, 8)

        # ── Window-management controls ──
        ontop_btn = Gtk.ToggleButton(label="📌 Always on Top")
        ontop_btn.connect("toggled", self._on_ontop_toggled)
        toolbar.pack_end(ontop_btn, False, False, 0)

        main_win_btn = Gtk.ToggleButton(label="🙈 Hide Main Window")
        main_win_btn.connect("toggled", self._on_toggle_main_window)
        toolbar.pack_end(main_win_btn, False, False, 0)
        self.main_win_btn = main_win_btn

        vbox.pack_start(toolbar_scroll, False, False, 0)

        # ── Main paned area ──
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(240)
        vbox.pack_start(paned, True, True, 0)

        # Left — stage list
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        stage_hdr = Gtk.Box(spacing=6)
        stage_hdr.set_border_width(8)
        stage_lbl = Gtk.Label()
        stage_lbl.set_markup("<b>Stages</b>")
        stage_lbl.set_halign(Gtk.Align.START)
        stage_hdr.pack_start(stage_lbl, True, True, 0)
        left.pack_start(stage_hdr, False, False, 0)

        stage_scroll = Gtk.ScrolledWindow()
        self.stage_list = Gtk.ListBox()
        self.stage_list.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.stage_list.connect("row-selected", self._on_stage_selected)
        self.stage_list.connect("key-press-event", self._on_key_press)
        self.stage_list.connect("button-press-event", self._on_stage_list_button_press)
        self.stage_list.connect("button-press-event", self._on_stage_click_clear_selection)
        stage_scroll.add(self.stage_list)
        left.pack_start(stage_scroll, True, True, 0)

        # Remove stage button under list
        remove_stage_btn = Gtk.Button(label="🗑 Remove Selected Stage")
        remove_stage_btn.set_margin_top(4)
        remove_stage_btn.set_margin_bottom(4)
        remove_stage_btn.connect("clicked", self._remove_stage)
        left.pack_start(remove_stage_btn, False, False, 0)

        paned.pack1(left, resize=False, shrink=False)

        # Right — items + notes for selected stage
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        right_hdr = Gtk.Box(spacing=6)
        right_hdr.set_border_width(8)
        self.stage_title_lbl = Gtk.Label()
        self.stage_title_lbl.set_markup("<b>Select a stage</b>")
        self.stage_title_lbl.set_halign(Gtk.Align.START)
        self.stage_title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        right_hdr.pack_start(self.stage_title_lbl, True, True, 0)

        self.stage_progress_lbl = Gtk.Label(label="")
        right_hdr.pack_end(self.stage_progress_lbl, False, False, 0)
        right.pack_start(right_hdr, False, False, 0)

        right.pack_start(Gtk.Separator(), False, False, 0)

        # Checklist items scroll
        items_scroll = Gtk.ScrolledWindow()
        items_scroll.set_min_content_height(220)
        self.items_list = Gtk.ListBox()
        self.items_list.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
        self.items_list.connect("row-selected", self._on_item_selected)
        self.items_list.connect("key-press-event", self._on_key_press)
        self.items_list.connect("button-press-event", self._on_items_list_button_press)
        self.items_list.connect("button-press-event", self._on_item_click_clear_selection)
        items_scroll.add(self.items_list)
        right.pack_start(items_scroll, True, True, 0)

        remove_item_btn = Gtk.Button(label="🗑 Remove Selected Item")
        remove_item_btn.set_margin_top(4)
        remove_item_btn.set_margin_bottom(4)
        remove_item_btn.connect("clicked", self._remove_item)
        right.pack_start(remove_item_btn, False, False, 0)

        right.pack_start(Gtk.Separator(), False, False, 0)

        # Notes
        self.notes_hdr = Gtk.Label()
        self.notes_hdr.set_markup("<b>Stage Notes</b>")
        self.notes_hdr.set_halign(Gtk.Align.START)
        self.notes_hdr.set_margin_start(8)
        self.notes_hdr.set_margin_top(6)
        right.pack_start(self.notes_hdr, False, False, 0)

        notes_scroll = Gtk.ScrolledWindow()
        notes_scroll.set_min_content_height(100)
        self.notes_view = Gtk.TextView()
        self.notes_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.notes_view.get_style_context().add_class("notes-view")
        self.notes_buf = self.notes_view.get_buffer()
        self.notes_buf.connect("changed", self._on_notes_changed)
        notes_scroll.add(self.notes_view)
        notes_scroll.set_margin_start(8)
        notes_scroll.set_margin_end(8)
        notes_scroll.set_margin_bottom(8)
        right.pack_start(notes_scroll, False, False, 0)

        paned.pack2(right, resize=True, shrink=False)

        self._set_right_enabled(False)

    # ── Stage list ───────────────────────────────────────────────────────────

    def _refresh_stage_list(self, keep_selection=True):
        prev_index = self.selected_stage_index

        for child in self.stage_list.get_children():
            self.stage_list.remove(child)

        stages = self.project_data.get("stages", [])

        if not stages:
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            lbl = Gtk.Label(label="No stages yet.\nUse 'Add Stage' or import a roadmap.")
            lbl.set_justify(Gtk.Justification.CENTER)
            lbl.set_margin_top(16)
            row.add(lbl)
            self.stage_list.add(row)
        else:
            for i, stage in enumerate(stages):
                row = self._make_stage_row(i, stage)
                self.stage_list.add(row)

        self.stage_list.show_all()
        self._update_overall_progress()

        if keep_selection and prev_index is not None and 0 <= prev_index < len(stages):
            row = self.stage_list.get_row_at_index(prev_index)
            if row is not None:
                self.stage_list.select_row(row)
                return

        # Default: select first stage if any
        if stages:
            row = self.stage_list.get_row_at_index(0)
            if row is not None:
                self.stage_list.select_row(row)
        else:
            self.selected_stage_index = None
            self._set_right_enabled(False)

    def _make_stage_row(self, index, stage):
        row = Gtk.ListBoxRow()
        row.stage_index = index
        row.get_style_context().add_class("stage-row")

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        vbox.set_border_width(8)

        title_lbl = Gtk.Label(label=stage.get("title", "Untitled"))
        title_lbl.set_halign(Gtk.Align.START)
        title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        title_lbl.get_style_context().add_class("stage-title")
        vbox.pack_start(title_lbl, False, False, 0)

        done, total = checklists.progress_for_stage(stage)
        prog_lbl = Gtk.Label(label=f"{done} / {total} complete")
        prog_lbl.set_halign(Gtk.Align.START)
        prog_lbl.get_style_context().add_class("stage-progress")
        vbox.pack_start(prog_lbl, False, False, 0)

        row.add(vbox)
        return row

    def _on_stage_selected(self, listbox, row):
        if row is None or not hasattr(row, "stage_index"):
            self.selected_stage_index = None
            self._set_right_enabled(False)
            return

        self.selected_stage_index = row.stage_index
        self.selected_item_index = None
        self._set_right_enabled(True)
        self._refresh_items_list()
        self._refresh_stage_header()
        self._load_notes()

    def _refresh_stage_header(self):
        stage = self._current_stage()
        if stage is None:
            self.stage_title_lbl.set_markup("<b>Select a stage</b>")
            self.stage_progress_lbl.set_text("")
            return

        title = stage.get("title", "Untitled")
        self.stage_title_lbl.set_markup(f"<b>{title}</b>")

        done, total = checklists.progress_for_stage(stage)
        self.stage_progress_lbl.set_text(f"{done} / {total} complete")

    def _set_right_enabled(self, enabled: bool):
        for w in [self.items_list, self.notes_view]:
            w.set_sensitive(enabled)
        if not enabled:
            self.stage_title_lbl.set_markup("<b>Select a stage</b>")
            self.stage_progress_lbl.set_text("")
            for child in self.items_list.get_children():
                self.items_list.remove(child)
            self.items_list.show_all()
            self.notes_buf.handler_block_by_func(self._on_notes_changed)
            self.notes_buf.set_text("")
            self.notes_buf.handler_unblock_by_func(self._on_notes_changed)

    def _current_stage(self):
        if self.selected_stage_index is None:
            return None
        stages = self.project_data.get("stages", [])
        if 0 <= self.selected_stage_index < len(stages):
            return stages[self.selected_stage_index]
        return None

    # ── Items list ───────────────────────────────────────────────────────────

    def _refresh_items_list(self):
        for child in self.items_list.get_children():
            self.items_list.remove(child)

        stage = self._current_stage()
        if stage is None:
            self.items_list.show_all()
            return

        items = stage.get("items", [])

        if not items:
            row = Gtk.ListBoxRow()
            row.set_selectable(False)
            lbl = Gtk.Label(label="No items yet. Use 'Add Item'.")
            lbl.get_style_context().add_class("dim-label")
            lbl.set_margin_top(8)
            row.add(lbl)
            self.items_list.add(row)
        else:
            for i, item in enumerate(items):
                row = self._make_item_row(i, item)
                self.items_list.add(row)

        self.items_list.show_all()

    def _make_item_row(self, index, item):
        row = Gtk.ListBoxRow()
        row.item_index = index
        row.get_style_context().add_class("item-row")

        hbox = Gtk.Box(spacing=8)
        hbox.set_border_width(6)

        check = Gtk.CheckButton()
        check.set_active(bool(item.get("done")))
        check.connect("toggled", self._on_item_toggled, index)
        hbox.pack_start(check, False, False, 0)

        lbl = Gtk.Label(label=item.get("text", ""))
        lbl.set_halign(Gtk.Align.START)
        lbl.set_line_wrap(True)
        lbl.set_xalign(0.0)
        if item.get("done"):
            lbl.get_style_context().add_class("item-text-done")
        hbox.pack_start(lbl, True, True, 0)

        if item.get("description", "").strip():
            desc_badge = Gtk.Label(label="📝")
            desc_badge.set_tooltip_text("This task has a description. Click the task to view/edit it below.")
            hbox.pack_end(desc_badge, False, False, 0)

        row.add(hbox)
        return row

    def _on_item_toggled(self, check, index):
        stage = self._current_stage()
        if stage is None:
            return
        items = stage.get("items", [])
        if 0 <= index < len(items):
            items[index]["done"] = check.get_active()

        self._refresh_items_list()
        self._refresh_stage_header()
        self._refresh_stage_list_progress_only()
        self._update_overall_progress()
        self._mark_dirty()

    def _refresh_stage_list_progress_only(self):
        """Lightweight refresh of progress labels in the stage list without losing selection."""
        for row in self.stage_list.get_children():
            if not hasattr(row, "stage_index"):
                continue
            stage = self.project_data["stages"][row.stage_index]
            done, total = checklists.progress_for_stage(stage)
            # vbox -> [title_lbl, prog_lbl]
            vbox = row.get_child()
            children = vbox.get_children()
            if len(children) >= 2:
                children[1].set_text(f"{done} / {total} complete")

    def _update_overall_progress(self):
        done, total = checklists.progress_for_project(self.project_data)
        self.overall_progress_lbl.set_text(f"{done} / {total} complete")

    # ── Right-click context menus ───────────────────────────────────────────

    def _on_stage_list_button_press(self, widget, event):
        if event.button != 3:  # right-click only
            return False

        row = self.stage_list.get_row_at_y(int(event.y))
        if row is None or not hasattr(row, "stage_index"):
            return False

        self.stage_list.select_row(row)
        index = row.stage_index

        menu = Gtk.Menu()

        def add_item(label, cb, sensitive=True):
            mi = Gtk.MenuItem(label=label)
            mi.set_sensitive(sensitive)
            mi.connect("activate", cb)
            menu.append(mi)

        stages = self.project_data.get("stages", [])

        add_item("➕ Add Stage", lambda _: self._add_stage(None))
        add_item("✏ Rename Stage", lambda _: self._rename_stage(index))
        add_item("📄 Duplicate Stage", lambda _: self._duplicate_stage(index))
        menu.append(Gtk.SeparatorMenuItem())
        add_item("⬆ Move Up", lambda _: self._move_stage(index, -1), sensitive=index > 0)
        add_item("⬇ Move Down", lambda _: self._move_stage(index, 1), sensitive=index < len(stages) - 1)
        menu.append(Gtk.SeparatorMenuItem())
        add_item("➕ Add Item Here", lambda _: self._add_item(None))
        add_item("☑ Mark All Done", lambda _: self._set_all_items_done(index, True))
        add_item("☐ Mark All Undone", lambda _: self._set_all_items_done(index, False))
        add_item("🧹 Clear Completed Items", lambda _: self._clear_completed_items(index))
        menu.append(Gtk.SeparatorMenuItem())
        add_item("🗑 Remove Stage", lambda _: self._remove_stage(None))

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    def _on_items_list_button_press(self, widget, event):
        if event.button != 3:  # right-click only
            return False

        stage = self._current_stage()
        if stage is None:
            return False

        row = self.items_list.get_row_at_y(int(event.y))
        items = stage.get("items", [])

        menu = Gtk.Menu()

        def add_item(label, cb, sensitive=True):
            mi = Gtk.MenuItem(label=label)
            mi.set_sensitive(sensitive)
            mi.connect("activate", cb)
            menu.append(mi)

        add_item("➕ Add Item", lambda _: self._add_item(None))

        if row is not None and hasattr(row, "item_index"):
            self.items_list.select_row(row)
            index = row.item_index

            menu.append(Gtk.SeparatorMenuItem())
            add_item("✏ Edit Item", lambda _: self._edit_item(index))
            add_item("☑ Toggle Done", lambda _: self._toggle_item_done(index))
            add_item("📋 Copy Item Text", lambda _: self._copy_item_text(index))
            add_item("📄 Duplicate Item", lambda _: self._duplicate_item(index))
            menu.append(Gtk.SeparatorMenuItem())
            add_item("⬆ Move Up", lambda _: self._move_item(index, -1), sensitive=index > 0)
            add_item("⬇ Move Down", lambda _: self._move_item(index, 1), sensitive=index < len(items) - 1)

            other_stages = [
                (i, s) for i, s in enumerate(self.project_data.get("stages", []))
                if i != self.selected_stage_index
            ]
            if other_stages:
                menu.append(Gtk.SeparatorMenuItem())
                move_menu = Gtk.Menu()
                move_item = Gtk.MenuItem(label="➡ Move to Stage…")
                move_item.set_submenu(move_menu)
                for i, s in other_stages:
                    sub = Gtk.MenuItem(label=s.get("title", "Untitled"))
                    sub.connect("activate", lambda _, src=index, dst=i: self._move_item_to_stage(src, dst))
                    move_menu.append(sub)
                menu.append(move_item)

            menu.append(Gtk.SeparatorMenuItem())
            add_item("🗑 Remove Item", lambda _: self._remove_item(None))

        menu.show_all()
        menu.popup_at_pointer(event)
        return True

    # ── Stage context-menu actions ──────────────────────────────────────────

    def _rename_stage(self, index):
        stages = self.project_data.get("stages", [])
        if not (0 <= index < len(stages)):
            return
        stage = stages[index]

        dlg = Gtk.Dialog(title="Rename Stage", transient_for=self, flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        box = dlg.get_content_area()
        box.set_border_width(12)
        box.set_spacing(8)

        lbl = Gtk.Label(label="Stage title:")
        lbl.set_halign(Gtk.Align.START)
        box.pack_start(lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_text(stage.get("title", ""))
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)

        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK:
            new_title = entry.get_text().strip()
            if new_title:
                stage["title"] = new_title
                self._refresh_stage_list()
                self._refresh_stage_header()
                self._mark_dirty()
        dlg.destroy()

    def _duplicate_stage(self, index):
        stages = self.project_data.get("stages", [])
        if not (0 <= index < len(stages)):
            return
        import copy
        clone = copy.deepcopy(stages[index])
        clone["title"] = clone.get("title", "Untitled") + " (copy)"
        stages.insert(index + 1, clone)
        self.selected_stage_index = index + 1
        self._refresh_stage_list()
        self._mark_dirty()

    def _move_stage(self, index, direction):
        stages = self.project_data.get("stages", [])
        new_index = index + direction
        if not (0 <= new_index < len(stages)):
            return
        stages[index], stages[new_index] = stages[new_index], stages[index]
        self.selected_stage_index = new_index
        self._refresh_stage_list()
        self._mark_dirty()

    def _set_all_items_done(self, index, done):
        stages = self.project_data.get("stages", [])
        if not (0 <= index < len(stages)):
            return
        for item in stages[index].get("items", []):
            item["done"] = done

        if index == self.selected_stage_index:
            self._refresh_items_list()
            self._refresh_stage_header()

        self._refresh_stage_list_progress_only()
        self._update_overall_progress()
        self._mark_dirty()

    # ── Item context-menu actions ───────────────────────────────────────────

    def _edit_item(self, index):
        stage = self._current_stage()
        if stage is None:
            return
        items = stage.get("items", [])
        if not (0 <= index < len(items)):
            return

        dlg = Gtk.Dialog(title="Edit Item", transient_for=self, flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dlg.set_default_size(520, 320)
        box = dlg.get_content_area()
        box.set_border_width(12)
        box.set_spacing(8)

        lbl = Gtk.Label(label="Item text:")
        lbl.set_halign(Gtk.Align.START)
        box.pack_start(lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_text(items[index].get("text", ""))
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)

        desc_lbl = Gtk.Label(label="Description (optional):")
        desc_lbl.set_halign(Gtk.Align.START)
        box.pack_start(desc_lbl, False, False, 0)

        desc_scroll = Gtk.ScrolledWindow()
        desc_scroll.set_min_content_height(120)
        desc_view = Gtk.TextView()
        desc_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        desc_buf = desc_view.get_buffer()
        desc_buf.set_text(items[index].get("description", ""))
        desc_scroll.add(desc_view)
        box.pack_start(desc_scroll, True, True, 0)

        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK:
            new_text = entry.get_text().strip()
            start, end = desc_buf.get_bounds()
            new_desc = desc_buf.get_text(start, end, False).strip()
            if new_text:
                items[index]["text"] = new_text
                items[index]["description"] = new_desc
                self._refresh_items_list()
                self._mark_dirty()
        dlg.destroy()
    def _toggle_item_done(self, index):
        stage = self._current_stage()
        if stage is None:
            return
        items = stage.get("items", [])
        if 0 <= index < len(items):
            items[index]["done"] = not items[index].get("done", False)
            self._refresh_items_list()
            self._refresh_stage_header()
            self._refresh_stage_list_progress_only()
            self._update_overall_progress()
            self._mark_dirty()

    def _move_item(self, index, direction):
        stage = self._current_stage()
        if stage is None:
            return
        items = stage.get("items", [])
        new_index = index + direction
        if not (0 <= new_index < len(items)):
            return
        items[index], items[new_index] = items[new_index], items[index]
        self._refresh_items_list()
        self._mark_dirty()

    def _move_item_to_stage(self, item_index, target_stage_index):
        stage = self._current_stage()
        if stage is None:
            return
        items = stage.get("items", [])
        if not (0 <= item_index < len(items)):
            return

        stages = self.project_data.get("stages", [])
        if not (0 <= target_stage_index < len(stages)):
            return

        item = items.pop(item_index)
        stages[target_stage_index].setdefault("items", []).append(item)

        self._refresh_items_list()
        self._refresh_stage_header()
        self._refresh_stage_list_progress_only()
        self._update_overall_progress()
        self._mark_dirty()

    def _copy_item_text(self, index):
        stage = self._current_stage()
        if stage is None:
            return

        items = stage.get("items", [])
        if not (0 <= index < len(items)):
            return

        from gi.repository import Gdk
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = items[index].get("text", "")
        desc = items[index].get("description", "").strip()
        if desc:
            text += "\nDescript: " + desc
        clipboard.set_text(text, -1)

    def _duplicate_item(self, index):
        stage = self._current_stage()
        if stage is None:
            return

        items = stage.get("items", [])
        if not (0 <= index < len(items)):
            return

        import copy
        clone = copy.deepcopy(items[index])
        clone["text"] = clone.get("text", "") + " (copy)"
        items.insert(index + 1, clone)

        self._refresh_items_list()
        self._refresh_stage_header()
        self._refresh_stage_list_progress_only()
        self._update_overall_progress()
        self._mark_dirty()

    def _clear_completed_items(self, stage_index):
        stages = self.project_data.get("stages", [])
        if not (0 <= stage_index < len(stages)):
            return

        stage = stages[stage_index]
        old_items = stage.get("items", [])
        stage["items"] = [item for item in old_items if not item.get("done")]

        if stage_index == self.selected_stage_index:
            self._refresh_items_list()
            self._refresh_stage_header()

        self._refresh_stage_list_progress_only()
        self._update_overall_progress()
        self._mark_dirty()

    # ── Notes ────────────────────────────────────────────────────────────────

    def _load_notes(self):
        self.selected_item_index = None
        if hasattr(self, "notes_hdr"):
            self.notes_hdr.set_markup("<b>Stage Notes</b>")

        stage = self._current_stage()
        notes = stage.get("notes", "") if stage else ""

        self.notes_buf.handler_block_by_func(self._on_notes_changed)
        self.notes_buf.set_text(notes)
        self.notes_buf.handler_unblock_by_func(self._on_notes_changed)

    def _on_item_selected(self, listbox, row):
        if row is None or not hasattr(row, "item_index"):
            return

        self.selected_item_index = row.item_index
        self._load_task_description(row.item_index)

    def _load_task_description(self, index):
        stage = self._current_stage()
        if stage is None:
            return

        items = stage.get("items", [])
        if not (0 <= index < len(items)):
            return

        if hasattr(self, "notes_hdr"):
            self.notes_hdr.set_markup("<b>Task Description</b>")

        desc = items[index].get("description", "")

        self.notes_buf.handler_block_by_func(self._on_notes_changed)
        self.notes_buf.set_text(desc)
        self.notes_buf.handler_unblock_by_func(self._on_notes_changed)

    def _on_notes_changed(self, buf):
        stage = self._current_stage()
        if stage is None:
            return

        start, end = buf.get_bounds()
        text = buf.get_text(start, end, False)

        if self.selected_item_index is not None:
            items = stage.get("items", [])
            if 0 <= self.selected_item_index < len(items):
                items[self.selected_item_index]["description"] = text
        else:
            stage["notes"] = text

        self._mark_dirty()

    # ── Stage / item add & remove ───────────────────────────────────────────

    def _add_stage(self, _):
        dlg = Gtk.Dialog(title="Add Stage", transient_for=self, flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        box = dlg.get_content_area()
        box.set_border_width(12)
        box.set_spacing(8)

        lbl = Gtk.Label(label="Stage title:")
        lbl.set_halign(Gtk.Align.START)
        box.pack_start(lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)

        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK:
            title = entry.get_text().strip()
            if title:
                self.project_data.setdefault("stages", []).append(
                    checklists.new_stage(title)
                )
                self.selected_stage_index = len(self.project_data["stages"]) - 1
                self._refresh_stage_list()
                self._mark_dirty()
        dlg.destroy()

    def _remove_stage(self, _):
        if self.selected_stage_index is None:
            return

        stages = self.project_data.get("stages", [])
        if not (0 <= self.selected_stage_index < len(stages)):
            return

        stage = stages[self.selected_stage_index]

        confirm = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove stage '{stage.get('title', 'Untitled')}'?"
        )
        confirm.format_secondary_text("This will also remove all of its checklist items.")
        response = confirm.run()
        confirm.destroy()

        if response == Gtk.ResponseType.YES:
            stages.pop(self.selected_stage_index)
            self.selected_stage_index = None
            self._refresh_stage_list(keep_selection=False)
            self._mark_dirty()

    def _add_item(self, _):
        stage = self._current_stage()
        if stage is None:
            self._show_info("Select or create a stage first.")
            return

        dlg = Gtk.Dialog(title="Add Item", transient_for=self, flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        Gtk.STOCK_OK, Gtk.ResponseType.OK)
        dlg.set_default_size(520, 300)
        box = dlg.get_content_area()
        box.set_border_width(12)
        box.set_spacing(8)

        lbl = Gtk.Label(label="Item text:")
        lbl.set_halign(Gtk.Align.START)
        box.pack_start(lbl, False, False, 0)

        entry = Gtk.Entry()
        entry.set_activates_default(True)
        box.pack_start(entry, False, False, 0)

        desc_lbl = Gtk.Label(label="Description (optional):")
        desc_lbl.set_halign(Gtk.Align.START)
        box.pack_start(desc_lbl, False, False, 0)

        desc_scroll = Gtk.ScrolledWindow()
        desc_scroll.set_min_content_height(100)
        desc_view = Gtk.TextView()
        desc_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        desc_buf = desc_view.get_buffer()
        desc_scroll.add(desc_view)
        box.pack_start(desc_scroll, True, True, 0)

        dlg.set_default_response(Gtk.ResponseType.OK)
        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK:
            text = entry.get_text().strip()
            start, end = desc_buf.get_bounds()
            description = desc_buf.get_text(start, end, False).strip()
            if text:
                stage.setdefault("items", []).append(checklists.new_item(text, description=description))
                self._refresh_items_list()
                self._refresh_stage_header()
                self._refresh_stage_list_progress_only()
                self._update_overall_progress()
                self._mark_dirty()
        dlg.destroy()
    def _remove_item(self, _):
        stage = self._current_stage()
        if stage is None:
            return

        row = self.items_list.get_selected_row()
        if row is None or not hasattr(row, "item_index"):
            self._show_info("Select an item to remove first.")
            return

        items = stage.get("items", [])
        index = row.item_index
        if 0 <= index < len(items):
            items.pop(index)
            self.selected_item_index = None
            self._load_notes()

        self._refresh_items_list()
        self._refresh_stage_header()
        self._refresh_stage_list_progress_only()
        self._update_overall_progress()
        self._mark_dirty()

    # ── Import roadmap ───────────────────────────────────────────────────────

    def _markdown_import_prompt(self):
        project_name = os.path.basename(self.project_path) or "{name of the project}"
        return f"""Create a {project_name} checklist roadmap using the exact Multi-Commit markdown format below.

IMPORTANT OUTPUT RULE:
Your reply must contain ONLY ONE copyable code block.
Do not write any explanation before it.
Do not write any explanation after it.
Put the whole checklist inside the code block so I can copy and paste it directly into Multi-Commit.

Use this exact structure inside the code block:

# Stage 1 — Stage Name
Notes: Optional stage-level notes/context goes here.

- First task name
Descript: Explain what needs doing and why.

- Second task name
Descript: Explain what needs doing and why.

# Stage 2 — Another Stage
Notes: Optional stage-level notes/context goes here.

- Third task name
Descript: Explain what needs doing and why.

Rules:
- Do not use checkbox syntax like [ ] or [x].
- Use markdown headings for stages.
- Use normal bullet points for tasks.
- Use `Notes:` for stage-level notes.
- Use `Descript:` directly under each task for task descriptions.
- Keep task names short and clear.
- Keep descriptions useful but not massive.
- Do not use tables.
- Do not use nested checkboxes.
- Do not include anything outside the single code block."""


    def _copy_markdown_import_prompt(self, _=None):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(self._markdown_import_prompt(), -1)
        self._show_info("Markdown checklist format copied to clipboard.")

    def _open_import_dialog(self, _):
        dlg = Gtk.Dialog(title="Paste / Import Roadmap", transient_for=self, flags=0)
        dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                        "Import", Gtk.ResponseType.OK)
        dlg.set_default_size(600, 480)

        box = dlg.get_content_area()
        box.set_border_width(12)
        box.set_spacing(8)

        hint = Gtk.Label()
        hint.set_markup(
            "Paste a DevWise markdown roadmap below.\n"
            "<tt># Branch:</tt> creates a workstream / Git branch.\n"
            "<tt>## Issue:</tt> creates grouped work inside that branch.\n"
            "Use bullet lines (<tt>- Task</tt>) for <b>checklist items</b>.\n"
            "Use <tt>Done:</tt> and <tt>Descript:</tt> directly under tasks.\n"
            "Supported format: <tt># Branch → ## Issue → - Task → Done: → Descript:</tt>."
        )
        hint.set_halign(Gtk.Align.START)
        hint.set_line_wrap(True)
        box.pack_start(hint, False, False, 0)


        prompt_row = Gtk.Box(spacing=6)

        copy_prompt_btn = Gtk.Button(label="📋 Copy Branch/Issue Checklist Format")
        copy_prompt_btn.set_tooltip_text("Copy the markdown checklist format to clipboard")
        copy_prompt_btn.connect("clicked", self._copy_markdown_import_prompt)
        prompt_row.pack_start(copy_prompt_btn, False, False, 0)

        example_lbl = Gtk.Label(label="Markdown format: # Branch → ## Issue → - Task → Done: → Descript:")
        example_lbl.set_halign(Gtk.Align.START)
        example_lbl.get_style_context().add_class("dim-label")
        prompt_row.pack_start(example_lbl, True, True, 0)

        box.pack_start(prompt_row, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(280)
        text_view = Gtk.TextView()
        text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_view.set_monospace(True)
        text_buf = text_view.get_buffer()
        scroll.add(text_view)
        box.pack_start(scroll, True, True, 0)

        # Replace vs append option
        replace_check = Gtk.CheckButton(label="Replace existing stages (instead of appending)")
        replace_check.set_active(len(self.project_data.get("stages", [])) == 0)
        box.pack_start(replace_check, False, False, 0)

        dlg.show_all()

        if dlg.run() == Gtk.ResponseType.OK:
            start, end = text_buf.get_bounds()
            markdown_text = text_buf.get_text(start, end, False)

            if markdown_text.strip():
                imported = checklists.parse_markdown_roadmap(markdown_text)
                if imported:
                    checklists.merge_imported_stages(
                        self.project_data, imported,
                        replace=replace_check.get_active()
                    )
                    self.selected_stage_index = 0
                    self._refresh_stage_list(keep_selection=False)
                    self._mark_dirty()
                    activity.log_event(self.project_path, "checklist_imported", "Imported checklist roadmap")
                else:
                    self._show_info("No stages or items could be parsed from that text.")
            else:
                self._show_info("Paste box was empty — nothing imported.")

        dlg.destroy()

    # ── Export / Delete All ──────────────────────────────────────────────────

    def _export_checklist(self, _):
        markdown_text = checklists.export_markdown(
            self.project_path, os.path.basename(self.project_path)
        )

        dlg = Gtk.FileChooserDialog(
            title="Export Checklist as Markdown",
            transient_for=self,
            action=Gtk.FileChooserAction.SAVE,
            buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                    Gtk.STOCK_SAVE, Gtk.ResponseType.OK)
        )
        dlg.set_do_overwrite_confirmation(True)
        default_dir = os.path.expanduser("~/Projects/Code Reviews")
        os.makedirs(default_dir, exist_ok=True)
        dlg.set_current_folder(default_dir)
        dlg.set_current_name(f"{os.path.basename(self.project_path)}_checklist.md")

        if dlg.run() == Gtk.ResponseType.OK:
            out_path = dlg.get_filename()
            try:
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(markdown_text)
                activity.log_event(self.project_path, "checklist_exported", f"Exported checklist to {out_path}")
                self._show_info(f"Checklist exported to:\n{out_path}")
            except Exception as e:
                self._show_info(f"Failed to export:\n{e}", title="Error")

        dlg.destroy()

    def _delete_all_checklist(self, _):
        confirm1 = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Delete ALL checklist data for this project?"
        )
        confirm1.format_secondary_text(
            "This will remove every stage, item and note for this project.\n"
            "This cannot be undone."
        )
        r1 = confirm1.run()
        confirm1.destroy()
        if r1 != Gtk.ResponseType.YES:
            return

        confirm2 = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Are you absolutely sure?"
        )
        confirm2.format_secondary_text(
            f"Last chance — delete all checklist data for:\n{self.project_path}"
        )
        r2 = confirm2.run()
        confirm2.destroy()
        if r2 != Gtk.ResponseType.YES:
            return

        checklists.delete_project_data(self.project_path)
        self.project_data = {"stages": [], "created": None, "updated": None,
                            "autosave": self._autosave_enabled}
        self.selected_stage_index = None
        self._refresh_stage_list(keep_selection=False)
        self._dirty = False
        self._update_save_button_style()

    # ── Save / autosave ──────────────────────────────────────────────────────

    def _save(self):
        try:
            checklists.save_project_data(self.project_path, self.project_data)
            self._dirty = False
            self._update_save_button_style()
        except Exception as e:
            self._show_info(f"Failed to save checklist:\n{e}", title="Error")

    def _mark_dirty(self):
        self._dirty = True
        self._update_save_button_style()

        if self._autosave_enabled:
            self._schedule_autosave()

    def _schedule_autosave(self):
        from gi.repository import GLib
        if self._autosave_timeout:
            GLib.source_remove(self._autosave_timeout)

        def _do_save():
            self._save()
            self._autosave_timeout = None
            return False

        self._autosave_timeout = GLib.timeout_add(800, _do_save)

    def _update_save_button_style(self):
        ctx = self.save_btn.get_style_context()
        ctx.remove_class("save-btn-saved")
        ctx.remove_class("save-btn-unsaved")

        if self._dirty:
            ctx.add_class("save-btn-unsaved")
            self.save_btn.set_label("💾 Save (unsaved changes)")
        else:
            ctx.add_class("save-btn-saved")
            self.save_btn.set_label("💾 Saved")

    def _on_autosave_toggled(self, switch, _param):
        self._autosave_enabled = switch.get_active()
        self.project_data["autosave"] = self._autosave_enabled

        if self._autosave_enabled and self._dirty:
            self._schedule_autosave()
        else:
            self._mark_dirty()  # persist the toggle state itself via dirty flag

    def _on_ontop_toggled(self, btn):
        self.set_keep_above(btn.get_active())

    def _on_toggle_main_window(self, btn):
        if self.parent_window is None:
            btn.set_active(False)
            return

        if btn.get_active():
            self.parent_window.hide()
            btn.set_label("👁 Show Main Window")
        else:
            self.parent_window.show()
            self.parent_window.present()
            btn.set_label("🙈 Hide Main Window")

    def _restore_window_geometry(self):
        """
        Restore the last Checklist window position and size.

        This lets the Checklist reopen where the user last placed it,
        including a second monitor / gTile layout.
        """
        geom = settings.get("checklist_window_geometry") or {}

        try:
            width = int(geom.get("width", 640))
            height = int(geom.get("height", 480))
            self.set_default_size(max(320, width), max(240, height))

            x = geom.get("x")
            y = geom.get("y")

            if x is not None and y is not None:
                self.move(int(x), int(y))

        except Exception:
            # Fallback to normal default size if stored geometry is invalid.
            self.set_default_size(640, 480)

    def _save_window_geometry(self):
        """
        Save the current Checklist window position and size.

        GTK coordinates are global screen coordinates, so this should preserve
        second-monitor positions too.
        """
        try:
            x, y = self.get_position()
            width, height = self.get_size()

            if width < 200 or height < 150:
                return

            settings.set_value("checklist_window_geometry", {
                "x": int(x),
                "y": int(y),
                "width": int(width),
                "height": int(height),
            })

        except Exception:
            pass


    def _on_close(self, window, event):
        """Warn before closing if there are unsaved changes.
        Return False to allow close, True to cancel close.
        """
        self._save_window_geometry()

        if not self._dirty:
            self._restore_main_window_if_hidden()
            return False

        dlg = Gtk.MessageDialog(
            transient_for=self, flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Unsaved changes"
        )
        dlg.format_secondary_text(
            "You have unsaved checklist changes.\n"
            "Save before closing?"
        )
        dlg.add_button("Discard", Gtk.ResponseType.REJECT)
        dlg.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dlg.add_button("Save", Gtk.ResponseType.ACCEPT)
        dlg.set_default_response(Gtk.ResponseType.ACCEPT)

        response = dlg.run()
        dlg.destroy()

        if response == Gtk.ResponseType.ACCEPT:
            self._save()
            self._restore_main_window_if_hidden()
            return False

        if response == Gtk.ResponseType.REJECT:
            self._restore_main_window_if_hidden()
            return False

        return True

    def _restore_main_window_if_hidden(self):
        if (self.parent_window is not None
                and self.main_win_btn.get_active()
                and not self.parent_window.get_visible()):
            self.parent_window.show()
            self.parent_window.present()

    def _on_key_press(self, widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        shift = event.state & Gdk.ModifierType.SHIFT_MASK

        if ctrl and shift and event.keyval == Gdk.KEY_Delete:
            if widget == self.items_list:
                self._bulk_remove_selected_items()
            elif widget == self.stage_list:
                self._bulk_remove_selected_stages()
            return True

        return False

    def _bulk_remove_selected_items(self):
        stage = self._current_stage()
        if stage is None:
            return

        rows = self.items_list.get_selected_rows()
        indexes = sorted(
            [row.item_index for row in rows if hasattr(row, "item_index")],
            reverse=True
        )

        if not indexes:
            return

        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete {len(indexes)} selected checklist item(s)?"
        )

        response = dlg.run()
        dlg.destroy()

        if response == Gtk.ResponseType.YES:
            items = stage.get("items", [])
            for index in indexes:
                if 0 <= index < len(items):
                    items.pop(index)

            self._refresh_items_list()
            self._refresh_stage_header()
            self._refresh_stage_list_progress_only()
            self._update_overall_progress()
            self._mark_dirty()

    def _bulk_remove_selected_stages(self):
        rows = self.stage_list.get_selected_rows()
        indexes = sorted(
            [row.stage_index for row in rows if hasattr(row, "stage_index")],
            reverse=True
        )

        if not indexes:
            return

        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete {len(indexes)} selected stage(s)?"
        )
        dlg.format_secondary_text("This also deletes all checklist items inside those stages.")

        response = dlg.run()
        dlg.destroy()

        if response == Gtk.ResponseType.YES:
            stages = self.project_data.get("stages", [])
            for index in indexes:
                if 0 <= index < len(stages):
                    stages.pop(index)

            self.selected_stage_index = None
            self._refresh_stage_list(keep_selection=False)
            self._mark_dirty()

    def _show_info(self, message, title="Info"):
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

    def _on_stage_click_clear_selection(self, widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK

        if event.button == 1 and not ctrl:
            self.stage_list.unselect_all()

        return False

    def _on_item_click_clear_selection(self, widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK

        if event.button == 1 and not ctrl:
            self.items_list.unselect_all()

        return False


# ── Multi-Commit checklist resume patch v2 ──────────────────────────────────
#
# Fixes previous behaviour where the first auto-selected stage overwrote the
# saved resume position during window startup.

def _mc_resume_key(self):
    try:
        return os.path.abspath(os.path.expanduser(self.project_path))
    except Exception:
        return ""


def _mc_resume_store():
    store = settings.get("checklist_resume_state") or {}
    return store if isinstance(store, dict) else {}


def _mc_save_resume(self):
    if getattr(self, "_mc_resume_suppress_save", False):
        return

    key = self._mc_resume_key()
    if not key:
        return

    stage_index = getattr(self, "selected_stage_index", None)
    item_index = getattr(self, "selected_item_index", None)

    try:
        stage_row = self.stage_list.get_selected_row()
        if stage_row is not None and hasattr(stage_row, "stage_index"):
            stage_index = stage_row.stage_index
    except Exception:
        pass

    try:
        item_row = self.items_list.get_selected_row()
        if item_row is not None and hasattr(item_row, "item_index"):
            item_index = item_row.item_index
    except Exception:
        pass

    if stage_index is None:
        return

    store = _mc_resume_store()
    store[key] = {
        "stage": int(stage_index),
        "item": int(item_index) if item_index is not None else None,
    }
    settings.set_value("checklist_resume_state", store)


def _mc_restore_resume(self):
    key = self._mc_resume_key()
    saved = _mc_resume_store().get(key)

    if not saved:
        return False

    stages = self.project_data.get("stages", [])
    if not stages:
        return False

    try:
        stage_index = int(saved.get("stage", 0))
    except Exception:
        stage_index = 0

    stage_index = max(0, min(stage_index, len(stages) - 1))

    raw_item = saved.get("item", None)
    try:
        item_index = int(raw_item) if raw_item is not None else None
    except Exception:
        item_index = None

    self._mc_resume_suppress_save = True

    try:
        # Select the saved stage and rebuild the item list.
        self.selected_stage_index = stage_index
        self.selected_item_index = None

        stage_row = self.stage_list.get_row_at_index(stage_index)
        if stage_row is not None:
            try:
                self.stage_list.unselect_all()
            except Exception:
                pass
            self.stage_list.select_row(stage_row)
            try:
                stage_row.grab_focus()
            except Exception:
                pass

        # Force right side to match saved stage even if GTK signal timing is odd.
        self._set_right_enabled(True)
        self._refresh_items_list()
        self._refresh_stage_header()
        self._load_notes()

        # Restore item after rows exist.
        if item_index is not None:
            items = stages[stage_index].get("items", [])
            if items:
                item_index = max(0, min(item_index, len(items) - 1))
                item_row = self.items_list.get_row_at_index(item_index)

                if item_row is not None:
                    try:
                        self.items_list.unselect_all()
                    except Exception:
                        pass
                    self.items_list.select_row(item_row)
                    self.selected_item_index = item_index
                    self._load_task_description(item_index)
                    try:
                        item_row.grab_focus()
                    except Exception:
                        pass

        if hasattr(self, "stage_title_lbl"):
            title = stages[stage_index].get("title", "Untitled")
            self.stage_title_lbl.set_tooltip_text(f"Resumed: {title}")

    finally:
        self._mc_resume_suppress_save = False

    return False


if not getattr(ChecklistWindow, "_mc_resume_v2_applied", False):
    ChecklistWindow._mc_base_init = ChecklistWindow.__init__
    ChecklistWindow._mc_base_on_close = ChecklistWindow._on_close
    ChecklistWindow._mc_base_on_stage_selected = ChecklistWindow._on_stage_selected
    ChecklistWindow._mc_base_on_item_selected = ChecklistWindow._on_item_selected

    ChecklistWindow._mc_resume_key = _mc_resume_key
    ChecklistWindow._mc_save_resume = _mc_save_resume
    ChecklistWindow._mc_restore_resume = _mc_restore_resume

    def _mc_init_v2(self, *args, **kwargs):
        # Prevent the initial "select first stage" from overwriting saved state.
        self._mc_resume_suppress_save = True
        ChecklistWindow._mc_base_init(self, *args, **kwargs)
        self._mc_resume_suppress_save = False

        # Restore after GTK has created/shown stage + item rows.
        GLib.timeout_add(120, self._mc_restore_resume)

    def _mc_on_close_v2(self, *args, **kwargs):
        self._mc_save_resume()
        return ChecklistWindow._mc_base_on_close(self, *args, **kwargs)

    def _mc_on_stage_selected_v2(self, listbox, row):
        result = ChecklistWindow._mc_base_on_stage_selected(self, listbox, row)

        if row is not None and hasattr(row, "stage_index"):
            self.selected_stage_index = row.stage_index
            self.selected_item_index = None
            self._mc_save_resume()

        return result

    def _mc_on_item_selected_v2(self, listbox, row):
        result = ChecklistWindow._mc_base_on_item_selected(self, listbox, row)

        if row is not None and hasattr(row, "item_index"):
            self.selected_item_index = row.item_index
            self._mc_save_resume()

        return result

    ChecklistWindow.__init__ = _mc_init_v2
    ChecklistWindow._on_close = _mc_on_close_v2
    ChecklistWindow._on_stage_selected = _mc_on_stage_selected_v2
    ChecklistWindow._on_item_selected = _mc_on_item_selected_v2
    ChecklistWindow._mc_resume_v2_applied = True


# ── DevWise Branch/Issue checklist UI patch ─────────────────────────────────
try:
    import shlex
    from core import issues as dw_issues
    from core import git_ops as dw_git_ops
except Exception:
    shlex = None
    dw_issues = None
    dw_git_ops = None


def _dw_current_branch(self):
    try:
        return dw_git_ops.get_current_branch(self.project_path) if dw_git_ops else ""
    except Exception:
        return ""


def _dw_current_issue(self):
    if not dw_issues:
        return None

    try:
        active_id = self.project_data.get("active_issue_id")
        if active_id:
            issue = dw_issues.get_issue(self.project_path, active_id)
            if issue:
                return issue
        return dw_issues.active_issue(self.project_path)
    except Exception:
        return None


def _dw_issue_tasks_from_selection(self):
    stage = self._current_stage()
    if stage is None:
        return []

    items = stage.get("items", [])
    selected = []

    try:
        rows = self.items_list.get_selected_rows()
    except Exception:
        rows = []

    for row in rows:
        idx = getattr(row, "item_index", None)
        if idx is not None and 0 <= idx < len(items):
            selected.append(items[idx])

    if not selected and getattr(self, "selected_item_index", None) is not None:
        idx = self.selected_item_index
        if 0 <= idx < len(items):
            selected.append(items[idx])

    if not selected:
        selected = items[:]

    return [
        {
            "text": item.get("text", ""),
            "done": bool(item.get("done")),
            "description": item.get("description", ""),
        }
        for item in selected
        if item.get("text")
    ]


def _dw_add_branch_issue_bar(self):
    if getattr(self, "_dw_branch_issue_bar_added", False):
        return

    root = self.get_child()
    if root is None:
        return

    bar = Gtk.Box(spacing=8)
    bar.set_border_width(7)

    self.dw_branch_lbl = Gtk.Label(label="Branch: —")
    self.dw_branch_lbl.set_halign(Gtk.Align.START)
    bar.pack_start(self.dw_branch_lbl, False, False, 0)

    issue_lbl = Gtk.Label(label="Issue:")
    issue_lbl.set_halign(Gtk.Align.START)
    bar.pack_start(issue_lbl, False, False, 0)

    self.dw_issue_combo = Gtk.ComboBoxText()
    self.dw_issue_combo.set_tooltip_text("Active local issue for this checklist/project")
    self.dw_issue_combo.connect("changed", self._dw_on_issue_combo_changed)
    bar.pack_start(self.dw_issue_combo, False, False, 0)

    make_issue_btn = Gtk.Button(label="Create Issue From Selected")
    make_issue_btn.set_tooltip_text("Turns selected checklist item(s), or the current stage, into a local issue.")
    make_issue_btn.connect("clicked", self._dw_create_issue_from_selected)
    bar.pack_start(make_issue_btn, False, False, 0)

    branch_btn = Gtk.Button(label="Create/Switch Branch")
    branch_btn.set_tooltip_text("Creates or switches to the active issue branch.")
    branch_btn.connect("clicked", self._dw_create_or_switch_issue_branch)
    bar.pack_start(branch_btn, False, False, 0)

    focus_hint = Gtk.Label(label="Format: Branch → Issue → Task → Descript")
    focus_hint.set_halign(Gtk.Align.START)
    try:
        focus_hint.get_style_context().add_class("dim-label")
    except Exception:
        pass
    bar.pack_start(focus_hint, True, True, 0)

    root.pack_start(bar, False, False, 0)
    try:
        root.reorder_child(bar, 1)
    except Exception:
        pass

    self._dw_branch_issue_bar_added = True
    self._dw_refresh_issue_combo()
    self._dw_update_branch_issue_bar()
    root.show_all()


def _dw_refresh_issue_combo(self):
    if not hasattr(self, "dw_issue_combo") or not dw_issues:
        return

    self._dw_loading_issue_combo = True
    self.dw_issue_combo.remove_all()
    self.dw_issue_combo.append("_none", "No active issue")

    active_id = self.project_data.get("active_issue_id") or ""

    try:
        all_issues = dw_issues.list_issues(self.project_path)
    except Exception:
        all_issues = []

    for issue in all_issues:
        status = "✓ " if issue.get("status") == "closed" else ""
        self.dw_issue_combo.append(issue.get("id"), status + issue.get("title", "Untitled issue"))

    if active_id:
        self.dw_issue_combo.set_active_id(active_id)
    else:
        self.dw_issue_combo.set_active_id("_none")

    self._dw_loading_issue_combo = False


def _dw_update_branch_issue_bar(self):
    if not hasattr(self, "dw_branch_lbl"):
        return

    branch = self._dw_current_branch()
    active = self._dw_current_issue()
    stage = self._current_stage()

    label = f"Branch: {branch or 'unknown'}"
    if stage and stage.get("branch"):
        label += f"  |  Checklist branch: {stage.get('branch')}"

    self.dw_branch_lbl.set_text(label)

    if active and hasattr(self, "dw_issue_combo"):
        try:
            self.dw_issue_combo.set_active_id(active.get("id"))
        except Exception:
            pass


def _dw_on_issue_combo_changed(self, combo):
    if getattr(self, "_dw_loading_issue_combo", False):
        return

    issue_id = combo.get_active_id()

    if not issue_id or issue_id == "_none":
        self.project_data["active_issue_id"] = None
        return

    self.project_data["active_issue_id"] = issue_id

    stage = self._current_stage()
    issue = dw_issues.get_issue(self.project_path, issue_id) if dw_issues else None

    if stage is not None and issue:
        stage["issue_id"] = issue_id
        stage["issue"] = issue.get("title", "")
        stage["branch"] = issue.get("branch", "")

    try:
        dw_issues.set_active_issue(self.project_path, issue_id)
    except Exception:
        pass

    self._mark_dirty()
    self._dw_update_branch_issue_bar()


def _dw_create_issue_from_selected(self, _=None):
    if not dw_issues:
        self._show_info("Issue helper is unavailable.")
        return

    stage = self._current_stage()
    if stage is None:
        self._show_info("Select a stage first.")
        return

    tasks = self._dw_issue_tasks_from_selection()
    default_title = stage.get("issue") or stage.get("title", "New issue")

    dlg = Gtk.Dialog(title="Create Local Issue", transient_for=self, flags=0)
    dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Create Issue", Gtk.ResponseType.OK)
    dlg.set_default_size(520, 180)

    box = dlg.get_content_area()
    box.set_border_width(12)
    box.set_spacing(8)

    lbl = Gtk.Label(label="Issue title:")
    lbl.set_halign(Gtk.Align.START)
    box.pack_start(lbl, False, False, 0)

    entry = Gtk.Entry()
    entry.set_text(default_title)
    entry.set_activates_default(True)
    box.pack_start(entry, False, False, 0)

    hint = Gtk.Label(label=f"Tasks captured: {len(tasks)}")
    hint.set_halign(Gtk.Align.START)
    box.pack_start(hint, False, False, 0)

    dlg.set_default_response(Gtk.ResponseType.OK)
    dlg.show_all()
    response = dlg.run()
    title = entry.get_text().strip()
    dlg.destroy()

    if response != Gtk.ResponseType.OK or not title:
        return

    branch = stage.get("branch") or dw_issues.slugify(title)
    issue = dw_issues.create_issue(self.project_path, title, branch=branch, tasks=tasks, source="checklist")

    self.project_data["active_issue_id"] = issue.get("id")
    stage["issue_id"] = issue.get("id")
    stage["issue"] = issue.get("title")
    stage["branch"] = issue.get("branch")

    for item in stage.get("items", []):
        for task in tasks:
            if item.get("text") == task.get("text"):
                item["issue_id"] = issue.get("id")

    self._dw_refresh_issue_combo()
    self._dw_update_branch_issue_bar()
    self._refresh_stage_header()
    self._refresh_stage_list()
    self._mark_dirty()
    self._show_info(f"Created issue:\n{issue.get('title')}\n\nBranch:\n{issue.get('branch')}", title="Issue created")


def _dw_create_or_switch_issue_branch(self, _=None):
    if not dw_issues or not dw_git_ops:
        self._show_info("Git/issue helper unavailable.")
        return

    issue = self._dw_current_issue()

    if not issue:
        self._dw_create_issue_from_selected()
        issue = self._dw_current_issue()

    if not issue:
        return

    branch = issue.get("branch") or dw_issues.slugify(issue.get("title"))

    confirm = Gtk.MessageDialog(
        transient_for=self,
        flags=0,
        message_type=Gtk.MessageType.QUESTION,
        buttons=Gtk.ButtonsType.YES_NO,
        text=f"Create/switch to branch '{branch}'?"
    )
    confirm.format_secondary_text(
        "This only runs Git branch/checkout commands.\n"
        "It does not commit, push or delete anything."
    )
    response = confirm.run()
    confirm.destroy()

    if response != Gtk.ResponseType.YES:
        return

    q = shlex.quote(branch) if shlex else branch
    ok, existing = dw_git_ops.run_custom(self.project_path, f"git branch --list {q}")

    if ok and existing.strip():
        ok2, out = dw_git_ops.run_custom(self.project_path, f"git checkout {q}")
    else:
        ok2, out = dw_git_ops.run_custom(self.project_path, f"git checkout -b {q}")

    self._dw_update_branch_issue_bar()

    if ok2:
        self._show_info(f"Now on branch:\n{branch}", title="Branch ready")
    else:
        self._show_info(out or "Could not create/switch branch.", title="Branch error")


def _dw_mark_active_issue_closed(self, _=None):
    issue = self._dw_current_issue()
    if not issue or not dw_issues:
        return
    dw_issues.close_issue(self.project_path, issue.get("id"))
    self._dw_refresh_issue_combo()


def _dw_mark_active_issue_open(self, _=None):
    issue = self._dw_current_issue()
    if not issue or not dw_issues:
        return
    dw_issues.reopen_issue(self.project_path, issue.get("id"))
    self._dw_refresh_issue_combo()


def _dw_markdown_import_prompt(self):
    project_name = os.path.basename(self.project_path) or "{project}"
    return f"""Create a {project_name} DevWise checklist using this exact format.

IMPORTANT OUTPUT RULE:
Return only one copyable markdown code block. No explanation outside it.

Use this structure:

# Branch: feat/example-branch
Notes: Optional branch/workstream context.

## Issue: Short issue title
- First task
Descript: Useful detail for this task.

- Second task
Descript: Useful detail for this task.

## Issue: Another issue title
- Third task
Descript: Useful detail for this task.

Rules:
- Use Branch for the Git branch/workstream.
- Use Issue for grouped work.
- Use normal bullet points for tasks.
- Use Descript: directly under a task for task description.
- Do not use checkbox syntax like [ ] or [x].
- Keep task names short and descriptions useful.
- Do not use tables.
"""


def _dw_make_stage_row(self, index, stage):
    row = ChecklistWindow._dw_base_make_stage_row(self, index, stage)

    try:
        vbox = row.get_child()
        extra_bits = []
        if stage.get("branch"):
            extra_bits.append("🌿 " + stage.get("branch"))
        if stage.get("issue"):
            extra_bits.append("Issue: " + stage.get("issue"))

        if extra_bits:
            lbl = Gtk.Label(label="  ·  ".join(extra_bits))
            lbl.set_halign(Gtk.Align.START)
            try:
                lbl.get_style_context().add_class("stage-progress")
            except Exception:
                pass
            vbox.pack_start(lbl, False, False, 0)
            row.show_all()
    except Exception:
        pass

    return row


if not getattr(ChecklistWindow, "_dw_branch_issue_patch_applied", False):
    ChecklistWindow._dw_base_build = ChecklistWindow._build
    ChecklistWindow._dw_base_refresh_stage_header = ChecklistWindow._refresh_stage_header
    ChecklistWindow._dw_base_make_stage_row = ChecklistWindow._make_stage_row

    def _dw_build(self):
        ChecklistWindow._dw_base_build(self)
        self._dw_add_branch_issue_bar()

    def _dw_refresh_stage_header(self):
        result = ChecklistWindow._dw_base_refresh_stage_header(self)
        self._dw_update_branch_issue_bar()
        return result

    ChecklistWindow._build = _dw_build
    ChecklistWindow._refresh_stage_header = _dw_refresh_stage_header
    ChecklistWindow._make_stage_row = _dw_make_stage_row
    ChecklistWindow._markdown_import_prompt = _dw_markdown_import_prompt

    ChecklistWindow._dw_current_branch = _dw_current_branch
    ChecklistWindow._dw_current_issue = _dw_current_issue
    ChecklistWindow._dw_issue_tasks_from_selection = _dw_issue_tasks_from_selection
    ChecklistWindow._dw_add_branch_issue_bar = _dw_add_branch_issue_bar
    ChecklistWindow._dw_refresh_issue_combo = _dw_refresh_issue_combo
    ChecklistWindow._dw_update_branch_issue_bar = _dw_update_branch_issue_bar
    ChecklistWindow._dw_on_issue_combo_changed = _dw_on_issue_combo_changed
    ChecklistWindow._dw_create_issue_from_selected = _dw_create_issue_from_selected
    ChecklistWindow._dw_create_or_switch_issue_branch = _dw_create_or_switch_issue_branch
    ChecklistWindow._dw_mark_active_issue_closed = _dw_mark_active_issue_closed
    ChecklistWindow._dw_mark_active_issue_open = _dw_mark_active_issue_open

    ChecklistWindow._dw_branch_issue_patch_applied = True


# ── DevWise checklist export/update prompt patch ────────────────────────────
def _dw_current_checklist_markdown(self):
    return checklists.export_markdown(
        self.project_path,
        os.path.basename(os.path.abspath(self.project_path)),
    )


def _dw_update_checklist_prompt(self):
    current = self._dw_current_checklist_markdown()

    return (
        "Update this DevWise checklist.\n\n"
        "IMPORTANT OUTPUT RULE:\n"
        "Return only one copyable markdown code block. No explanation outside it.\n\n"
        "Goal:\n"
        "- Keep useful existing branches, issues, stages, tasks and descriptions.\n"
        "- Improve wording where helpful.\n"
        "- Add missing branches/issues/tasks if needed.\n"
        "- Do not delete existing work unless it is clearly duplicated or I explicitly ask.\n"
        "- Use Branch → Issue → Task → Descript format.\n"
        "- Do not use checkbox syntax like [ ] or [x].\n"
        "- Do not use tables.\n\n"
        "Format to return:\n\n"
        "# Branch: feat/example-branch\n"
        "Notes: Optional branch/workstream context.\n\n"
        "## Issue: Short issue title\n"
        "- Task name\n"
        "Descript: Useful detail for the task.\n\n"
        "Current checklist:\n\n"
        "```markdown\n"
        f"{current.rstrip()}\n"
        "```\n"
    )


def _dw_copy_to_clipboard(self, text, message="Copied."):
    Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text or "", -1)
    try:
        self._show_info(message)
    except Exception:
        pass


def _dw_text_page(self, text, editable=False):
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

    view = Gtk.TextView()
    view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    view.set_monospace(True)
    view.set_editable(editable)
    view.get_buffer().set_text(text or "")

    scroll.add(view)
    return scroll, view


def _dw_save_markdown_file(self, markdown_text):
    dlg = Gtk.FileChooserDialog(
        title="Save Current Checklist",
        transient_for=self,
        action=Gtk.FileChooserAction.SAVE,
        buttons=(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK,
        ),
    )
    dlg.set_do_overwrite_confirmation(True)

    default_dir = os.path.expanduser("~/Projects/Code Reviews")
    os.makedirs(default_dir, exist_ok=True)
    dlg.set_current_folder(default_dir)
    dlg.set_current_name(f"{os.path.basename(self.project_path)}_current_checklist.md")

    if dlg.run() == Gtk.ResponseType.OK:
        out_path = dlg.get_filename()
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            activity.log_event(self.project_path, "checklist_exported", f"Exported checklist to {out_path}")
            self._show_info(f"Checklist exported to:\n{out_path}")
        except Exception as e:
            self._show_info(f"Failed to export:\n{e}", title="Error")

    dlg.destroy()


def _dw_export_checklist_v2(self, _=None):
    current = self._dw_current_checklist_markdown()
    update_prompt = self._dw_update_checklist_prompt()

    dlg = Gtk.Dialog(title="Export / Update Checklist", transient_for=self, flags=0)
    dlg.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
    dlg.set_default_size(760, 620)

    box = dlg.get_content_area()
    box.set_border_width(10)
    box.set_spacing(8)

    hint = Gtk.Label()
    hint.set_markup(
        "<b>Current Checklist</b> = export/share your current roadmap.\n"
        "<b>Update Prompt</b> = paste into ChatGPT/Claude to improve or add to it without deleting useful existing work."
    )
    hint.set_halign(Gtk.Align.START)
    hint.set_line_wrap(True)
    box.pack_start(hint, False, False, 0)

    buttons = Gtk.Box(spacing=6)

    copy_current = Gtk.Button(label="📋 Copy Current Checklist")
    copy_current.connect("clicked", lambda _: self._dw_copy_to_clipboard(current, "Current checklist copied."))

    copy_prompt = Gtk.Button(label="🔁 Copy Update Prompt")
    copy_prompt.connect("clicked", lambda _: self._dw_copy_to_clipboard(update_prompt, "Checklist update prompt copied."))

    save_btn = Gtk.Button(label="💾 Save Current Checklist")
    save_btn.connect("clicked", lambda _: self._dw_save_markdown_file(current))

    buttons.pack_start(copy_current, False, False, 0)
    buttons.pack_start(copy_prompt, False, False, 0)
    buttons.pack_start(save_btn, False, False, 0)
    box.pack_start(buttons, False, False, 0)

    notebook = Gtk.Notebook()

    current_page, _current_view = self._dw_text_page(current, editable=False)
    prompt_page, _prompt_view = self._dw_text_page(update_prompt, editable=False)

    notebook.append_page(current_page, Gtk.Label(label="Current Checklist"))
    notebook.append_page(prompt_page, Gtk.Label(label="Update Prompt"))

    box.pack_start(notebook, True, True, 0)

    dlg.show_all()
    dlg.run()
    dlg.destroy()


def _dw_markdown_import_prompt_v2(self):
    project_name = os.path.basename(self.project_path) or "{project}"

    return f"""Create or update a {project_name} DevWise checklist.

IMPORTANT OUTPUT RULE:
Return only one copyable markdown code block. No explanation outside it.

Use this structure:

# Branch: feat/example-branch
Notes: Optional branch/workstream context.

## Issue: Short issue title
- First task name
Descript: Useful detail for this task.

- Second task name
Descript: Useful detail for this task.

Rules:
- Use Branch for the Git branch/workstream.
- Use Issue for grouped work.
- Use normal bullet points for tasks.
- Use Descript: directly under a task for task description.
- Do not use checkbox syntax like [ ] or [x].
- If updating an existing checklist, keep useful existing work and add/improve rather than deleting.
- Do not use tables.
"""


def _dw_copy_markdown_import_prompt_v2(self, _=None):
    self._dw_copy_to_clipboard(
        self._markdown_import_prompt(),
        "Markdown checklist/update format copied to clipboard.",
    )


ChecklistWindow._dw_current_checklist_markdown = _dw_current_checklist_markdown
ChecklistWindow._dw_update_checklist_prompt = _dw_update_checklist_prompt
ChecklistWindow._dw_copy_to_clipboard = _dw_copy_to_clipboard
ChecklistWindow._dw_text_page = _dw_text_page
ChecklistWindow._dw_save_markdown_file = _dw_save_markdown_file
ChecklistWindow._export_checklist = _dw_export_checklist_v2
ChecklistWindow._markdown_import_prompt = _dw_markdown_import_prompt_v2
ChecklistWindow._copy_markdown_import_prompt = _dw_copy_markdown_import_prompt_v2


# ── DevWise completed-status update prompt patch ────────────────────────────
def _dw_update_checklist_prompt_completed_status(self):
    current = self._dw_current_checklist_markdown()

    return (
        "Update this DevWise checklist.\n\n"
        "IMPORTANT OUTPUT RULE:\n"
        "Return only one copyable markdown code block. No explanation outside it.\n\n"
        "Goal:\n"
        "- Keep useful existing branches, issues, stages, tasks and descriptions.\n"
        "- Preserve completed work as completed context.\n"
        "- Do not turn completed tasks back into outstanding tasks unless I explicitly ask.\n"
        "- Add missing branches/issues/tasks where useful.\n"
        "- Improve wording where helpful.\n"
        "- Do not delete existing completed work unless it is clearly duplicated or I explicitly ask.\n\n"
        "Status rules:\n"
        "- Use Done: yes for tasks already completed.\n"
        "- Use Done: no for tasks still outstanding.\n"
        "- Use Stage Status: COMPLETE when every task in that stage/issue is done.\n"
        "- Use Stage Status: IN PROGRESS when some tasks are done and some remain.\n"
        "- Use Stage Status: NOT STARTED when no tasks are done yet.\n\n"
        "Format to return:\n\n"
        "# Branch: feat/example-branch\n"
        "Notes: Optional branch/workstream context.\n\n"
        "## Issue: Short issue title\n"
        "Stage Status: IN PROGRESS\n"
        "Stage Progress: 1 / 2 tasks complete\n"
        "- Task name\n"
        "Done: no\n"
        "Descript: Useful detail for the task.\n\n"
        "Rules:\n"
        "- Use Branch → Issue → Task → Done → Descript format.\n"
        "- Do not use checkbox syntax like [ ] or [x].\n"
        "- Do not use tables.\n\n"
        "Current checklist:\n\n"
        "```markdown\n"
        f"{current.rstrip()}\n"
        "```\n"
    )


def _dw_markdown_import_prompt_completed_status(self):
    project_name = os.path.basename(self.project_path) or "{project}"

    return f"""Create or update a {project_name} DevWise checklist.

IMPORTANT OUTPUT RULE:
Return only one copyable markdown code block. No explanation outside it.

Use this structure:

# Branch: feat/example-branch
Notes: Optional branch/workstream context.

## Issue: Short issue title
Stage Status: IN PROGRESS
Stage Progress: 0 / 2 tasks complete

- First task name
Done: no
Descript: Useful detail for this task.

- Second task name
Done: no
Descript: Useful detail for this task.

Rules:
- Use Branch for the Git branch/workstream.
- Use Issue for grouped work.
- Use normal bullet points for tasks.
- Use Done: yes/no under each task so completed work is preserved.
- Use Descript: directly under a task for task description.
- Do not use checkbox syntax like [ ] or [x].
- If updating an existing checklist, keep useful existing work and add/improve rather than deleting.
- Do not use tables.
"""


ChecklistWindow._dw_update_checklist_prompt = _dw_update_checklist_prompt_completed_status
ChecklistWindow._markdown_import_prompt = _dw_markdown_import_prompt_completed_status


# ── DevWise clean checklist AI prompt patch ─────────────────────────────────
def _dw_update_checklist_prompt_clean(self):
    current = self._dw_current_checklist_markdown()

    return (
        "Update this DevWise checklist.\n\n"
        "IMPORTANT OUTPUT RULE:\n"
        "Return only one clean markdown code block containing the updated checklist.\n"
        "Do not include explanations, citations, Source Checklist lines, contentReference tags, oaicite tags, or tables.\n\n"
        "Goal:\n"
        "- Keep useful existing branches, issues, tasks, notes and descriptions.\n"
        "- Preserve completed work as completed context.\n"
        "- Do not turn Done: yes tasks back into Done: no tasks unless explicitly asked.\n"
        "- Add missing tasks where useful.\n"
        "- Improve wording where helpful.\n"
        "- Do not delete completed work unless it is clearly duplicated.\n\n"
        "Required format:\n\n"
        "# Branch: feat/example-branch\n"
        "Notes: Optional branch/workstream context.\n\n"
        "## Issue: Short issue title\n"
        "Status: IN PROGRESS\n"
        "Progress: 1 / 2 tasks complete\n\n"
        "- Task name\n"
        "Done: no\n"
        "Descript: Useful task description.\n\n"
        "Rules:\n"
        "- Every task must have Done: yes or Done: no.\n"
        "- Every task should have Descript: directly underneath Done:.\n"
        "- Use Branch → Issue → Task → Done → Descript.\n"
        "- Do not use checkbox syntax like [ ] or [x].\n"
        "- Do not include Source Checklist or contentReference lines.\n\n"
        "Current checklist:\n\n"
        "```markdown\n"
        f"{current.rstrip()}\n"
        "```\n"
    )


def _dw_markdown_import_prompt_clean(self):
    project_name = os.path.basename(self.project_path) or "{project}"

    return f"""Create or update a {project_name} DevWise checklist.

IMPORTANT OUTPUT RULE:
Return only one clean markdown code block.
Do not include explanations, citations, Source Checklist lines, contentReference tags, oaicite tags, or tables.

Use this exact structure:

# Branch: feat/example-branch
Notes: Optional branch/workstream context.

## Issue: Short issue title
Status: IN PROGRESS
Progress: 0 / 2 tasks complete

- First task name
Done: no
Descript: Useful detail for this task.

- Second task name
Done: no
Descript: Useful detail for this task.

Rules:
- Use Branch for the Git branch/workstream.
- Use Issue for grouped work.
- Use normal bullet points for tasks.
- Every task must include Done: yes/no.
- Every task should include Descript: directly underneath Done:.
- Do not use checkbox syntax like [ ] or [x].
- If updating an existing checklist, keep useful existing work and add/improve rather than deleting.
- Do not include Source Checklist or contentReference lines.
- Do not use tables.
"""


ChecklistWindow._dw_update_checklist_prompt = _dw_update_checklist_prompt_clean
ChecklistWindow._markdown_import_prompt = _dw_markdown_import_prompt_clean

# Update visible helper label if the old one exists in the base UI.
try:
    ChecklistWindow._dw_clean_prompt_patch_applied = True
except Exception:
    pass


# ── DevWise Git Learning checklist prompt patch ─────────────────────────────
def _dw_branch_issue_import_prompt_with_done(self):
    project_name = os.path.basename(self.project_path) or "{project}"

    return f"""Create or update a {project_name} DevWise checklist.

IMPORTANT OUTPUT RULE:
Return only one copyable markdown code block. No explanation outside it.

Use this exact structure:

# Branch: feat/example-branch
Notes: Optional branch/workstream context.

## Issue: Short issue title
Status: NOT STARTED
Progress: 0 / 2 tasks complete

- First task name
Done: no
Descript: Useful detail for this task.

- Second task name
Done: no
Descript: Useful detail for this task.

Rules:
- Use Branch for the Git branch/workstream.
- Use Issue for grouped work.
- Use normal bullet points for tasks.
- Use Done: yes or Done: no directly under each task.
- Use Descript: directly under each task for task description.
- If updating an existing checklist, keep useful existing work and add/improve rather than deleting.
- Do not use checkbox syntax like [ ] or [x].
- Do not use tables.
"""


def _dw_update_checklist_prompt_with_done(self):
    current = checklists.export_markdown(
        self.project_path,
        os.path.basename(os.path.abspath(self.project_path)),
    )

    return (
        "Update this DevWise checklist.\\n\\n"
        "IMPORTANT OUTPUT RULE:\\n"
        "Return only one copyable markdown code block. No explanation outside it.\\n\\n"
        "Goal:\\n"
        "- Keep useful existing branches, issues, tasks, Done values and descriptions.\\n"
        "- Improve wording where helpful.\\n"
        "- Add missing branches/issues/tasks if needed.\\n"
        "- Do not delete existing work unless it is clearly duplicated or I explicitly ask.\\n"
        "- Use Branch → Issue → Task → Done → Descript format.\\n"
        "- Do not use checkbox syntax like [ ] or [x].\\n"
        "- Do not use tables.\\n\\n"
        "Current checklist:\\n\\n"
        "```markdown\\n"
        f"{current.rstrip()}\\n"
        "```\\n"
    )


ChecklistWindow._markdown_import_prompt = _dw_branch_issue_import_prompt_with_done
ChecklistWindow._dw_update_checklist_prompt = _dw_update_checklist_prompt_with_done


# ── DevWise active-only update prompt UI patch ──────────────────────────────
def _dw_active_checklist_markdown(self):
    return checklists.dw_active_markdown(
        self.project_path,
        os.path.basename(os.path.abspath(self.project_path)),
        include_completed_summary=True,
    )


def _dw_completed_summary_markdown(self):
    return checklists.dw_completed_summary(
        self.project_path,
        os.path.basename(os.path.abspath(self.project_path)),
    )


def _dw_full_checklist_markdown(self):
    return checklists.export_markdown(
        self.project_path,
        os.path.basename(os.path.abspath(self.project_path)),
    )


def _dw_update_prompt_active_only(self):
    return checklists.dw_update_prompt_active(
        self.project_path,
        os.path.basename(os.path.abspath(self.project_path)),
    )


def _dw_save_named_markdown_file(self, markdown_text, suffix):
    dlg = Gtk.FileChooserDialog(
        title="Save Checklist Markdown",
        transient_for=self,
        action=Gtk.FileChooserAction.SAVE,
        buttons=(
            Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
            Gtk.STOCK_SAVE, Gtk.ResponseType.OK,
        ),
    )
    dlg.set_do_overwrite_confirmation(True)

    default_dir = os.path.expanduser("~/Projects/Code Reviews")
    os.makedirs(default_dir, exist_ok=True)
    dlg.set_current_folder(default_dir)
    dlg.set_current_name(f"{os.path.basename(self.project_path)}_{suffix}.md")

    if dlg.run() == Gtk.ResponseType.OK:
        out_path = dlg.get_filename()
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(markdown_text)
            activity.log_event(self.project_path, "checklist_exported", f"Exported checklist to {out_path}")
            self._show_info(f"Checklist exported to:\n{out_path}")
        except Exception as e:
            self._show_info(f"Failed to export:\n{e}", title="Error")

    dlg.destroy()


def _dw_copy_active_update_prompt(self, *_):
    self._dw_copy_to_clipboard(
        self._dw_update_checklist_prompt(),
        "Active-work update prompt copied."
    )


def _dw_export_checklist_v3(self, _=None):
    active = self._dw_active_checklist_markdown()
    update_prompt = self._dw_update_checklist_prompt()
    full = self._dw_full_checklist_markdown()
    summary = self._dw_completed_summary_markdown()

    dlg = Gtk.Dialog(title="Export / Update Checklist", transient_for=self, flags=0)
    dlg.add_buttons(Gtk.STOCK_CLOSE, Gtk.ResponseType.CLOSE)
    dlg.set_default_size(840, 660)

    box = dlg.get_content_area()
    box.set_border_width(10)
    box.set_spacing(8)

    hint = Gtk.Label()
    hint.set_markup(
        "<b>Recommended default:</b> copy the Update Prompt. "
        "It focuses on active/incomplete work and only includes completed work as a short summary.\n"
        "<b>Full Checklist</b> is still available for archive/evidence."
    )
    hint.set_halign(Gtk.Align.START)
    hint.set_line_wrap(True)
    box.pack_start(hint, False, False, 0)

    buttons = Gtk.Box(spacing=6)

    copy_update = Gtk.Button(label="🔁 Copy Update Prompt")
    copy_update.set_tooltip_text("Best option for ChatGPT/Claude. Excludes full completed task detail.")
    copy_update.connect("clicked", lambda _: self._dw_copy_to_clipboard(update_prompt, "Active-work update prompt copied."))

    copy_active = Gtk.Button(label="📋 Copy Active Checklist")
    copy_active.set_tooltip_text("Copies active/incomplete work plus completed summary.")
    copy_active.connect("clicked", lambda _: self._dw_copy_to_clipboard(active, "Active checklist copied."))

    copy_full = Gtk.Button(label="📚 Copy Full Checklist")
    copy_full.set_tooltip_text("Copies everything, including completed task lists.")
    copy_full.connect("clicked", lambda _: self._dw_copy_to_clipboard(full, "Full checklist copied."))

    copy_summary = Gtk.Button(label="✅ Copy Completed Summary")
    copy_summary.connect("clicked", lambda _: self._dw_copy_to_clipboard(summary, "Completed summary copied."))

    save_active = Gtk.Button(label="💾 Save Active")
    save_active.connect("clicked", lambda _: self._dw_save_named_markdown_file(active, "active_checklist"))

    buttons.pack_start(copy_update, False, False, 0)
    buttons.pack_start(copy_active, False, False, 0)
    buttons.pack_start(copy_full, False, False, 0)
    buttons.pack_start(copy_summary, False, False, 0)
    buttons.pack_end(save_active, False, False, 0)
    box.pack_start(buttons, False, False, 0)

    notebook = Gtk.Notebook()

    active_page, _active_view = self._dw_text_page(active, editable=False)
    prompt_page, _prompt_view = self._dw_text_page(update_prompt, editable=False)
    full_page, _full_view = self._dw_text_page(full, editable=False)
    summary_page, _summary_view = self._dw_text_page(summary, editable=False)

    notebook.append_page(prompt_page, Gtk.Label(label="Update Prompt"))
    notebook.append_page(active_page, Gtk.Label(label="Active Checklist"))
    notebook.append_page(summary_page, Gtk.Label(label="Completed Summary"))
    notebook.append_page(full_page, Gtk.Label(label="Full Checklist"))

    box.pack_start(notebook, True, True, 0)

    dlg.show_all()
    dlg.run()
    dlg.destroy()


def _dw_markdown_import_prompt_active_default(self):
    project_name = os.path.basename(self.project_path) or "{project}"

    return f"""Create or update a {project_name} DevWise checklist.

IMPORTANT OUTPUT RULE:
Return only one clean markdown code block. No explanation outside it.
Do not include citations, source labels, contentReference tags, oaicite tags, or tables.

Use this exact structure:

# Branch: feat/example-branch
Notes: Optional branch/workstream context.

## Issue: Short issue title
Stage Status: IN PROGRESS
Stage Progress: 0 / 2 tasks complete

- First task name
Done: no
Descript: Useful detail for this task.

- Second task name
Done: no
Descript: Useful detail for this task.

Rules:
- Use Branch for the Git branch/workstream.
- Use Issue for grouped work.
- Use normal bullet points for tasks.
- Use Done: yes or Done: no under each task.
- Use Descript: directly under each task for task description.
- If updating an existing checklist, focus on active/incomplete work.
- Keep completed work only as completed context unless I explicitly ask for full completed tasks.
- Do not use checkbox syntax like [ ] or [x].
"""


ChecklistWindow._dw_active_checklist_markdown = _dw_active_checklist_markdown
ChecklistWindow._dw_completed_summary_markdown = _dw_completed_summary_markdown
ChecklistWindow._dw_full_checklist_markdown = _dw_full_checklist_markdown
ChecklistWindow._dw_update_checklist_prompt = _dw_update_prompt_active_only
ChecklistWindow._dw_copy_active_update_prompt = _dw_copy_active_update_prompt
ChecklistWindow._dw_save_named_markdown_file = _dw_save_named_markdown_file
ChecklistWindow._export_checklist = _dw_export_checklist_v3
ChecklistWindow._markdown_import_prompt = _dw_markdown_import_prompt_active_default


# ── DevWise branch-section checklist sidebar patch ──────────────────────────
def _dw_prompt_subject(self):
    project_name = os.path.basename(os.path.abspath(self.project_path)) or "this project"

    if project_name.strip().lower() == "devwise":
        return "DevWise checklist"

    return f"{project_name} DevWise checklist"


def _dw_markdown_import_prompt_branch_sections(self):
    subject = self._dw_prompt_subject()

    return f"""Create or update a {subject}.

IMPORTANT OUTPUT RULE:
Return only one clean markdown code block. No explanation outside it.
Do not include citations, source labels, contentReference tags, oaicite tags, or tables.

Use this exact structure:

# Branch: feat/example-branch
Notes: Optional branch/workstream context.

## Issue: Short issue title
Status: IN PROGRESS
Progress: 0 / 2 tasks complete

- First task name
Done: no
Descript: Useful detail for this task.

- Second task name
Done: no
Descript: Useful detail for this task.

Rules:
- Use Branch for the Git branch/workstream.
- Use Issue for grouped work.
- Use normal bullet points for tasks.
- Use Done: yes or Done: no under each task.
- Use Descript: directly under each task for task description.
- If updating an existing checklist, focus on active/incomplete work.
- Keep completed work only as completed context unless I explicitly ask for full completed tasks.
- Do not use checkbox syntax like [ ] or [x].
"""


def _dw_branch_key_for_stage(self, stage):
    return str(stage.get("branch", "") or "").strip() or "No branch"


def _dw_branch_groups(self):
    groups = []
    lookup = {}

    for index, stage in enumerate(self.project_data.get("stages", [])):
        branch = self._dw_branch_key_for_stage(stage)

        if branch not in lookup:
            group = {
                "branch": branch,
                "indexes": [],
                "done": 0,
                "total": 0,
            }
            lookup[branch] = group
            groups.append(group)

        d, t = checklists.progress_for_stage(stage)
        lookup[branch]["indexes"].append(index)
        lookup[branch]["done"] += d
        lookup[branch]["total"] += t

    return groups


def _dw_collapsed_set(self):
    if not hasattr(self, "_dw_collapsed_branches"):
        self._dw_collapsed_branches = set()
    return self._dw_collapsed_branches


def _dw_make_branch_header_row(self, group):
    row = Gtk.ListBoxRow()
    row.set_selectable(False)
    row.is_branch_header = True
    row.branch_key = group["branch"]

    collapsed = group["branch"] in self._dw_collapsed_set()
    arrow = "▸" if collapsed else "▾"

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

    box = Gtk.Box(spacing=6)
    box.set_border_width(7)

    btn = Gtk.Button(label=arrow)
    btn.set_relief(Gtk.ReliefStyle.NONE)
    btn.set_tooltip_text("Collapse / expand this branch")
    btn.connect("clicked", lambda _btn, b=group["branch"]: self._dw_toggle_branch(b))
    box.pack_start(btn, False, False, 0)

    title = Gtk.Label()
    title.set_markup(f"<b>{group['branch']}</b>")
    title.set_halign(Gtk.Align.START)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    box.pack_start(title, True, True, 0)

    issue_count = len(group["indexes"])
    done = group["done"]
    total = group["total"]
    status = "EMPTY" if total == 0 else ("COMPLETE" if done >= total else ("NOT STARTED" if done == 0 else "IN PROGRESS"))

    summary = Gtk.Label(label=f"{issue_count} issue(s) • {done}/{total} • {status}")
    summary.set_halign(Gtk.Align.END)
    summary.get_style_context().add_class("stage-progress")
    box.pack_end(summary, False, False, 0)

    outer.pack_start(box, False, False, 0)
    row.add(outer)
    return row


def _dw_toggle_branch(self, branch):
    collapsed = self._dw_collapsed_set()

    if branch in collapsed:
        collapsed.remove(branch)
    else:
        collapsed.add(branch)

    self._refresh_stage_list(keep_selection=True)


def _dw_find_stage_row(self, stage_index):
    try:
        wanted = int(stage_index)
    except Exception:
        return None

    for row in self.stage_list.get_children():
        if getattr(row, "stage_index", None) == wanted:
            return row

    return None


def _dw_refresh_stage_list_branch_grouped(self, keep_selection=True):
    prev_index = self.selected_stage_index

    stages = self.project_data.get("stages", [])

    # If the selected stage exists inside a collapsed branch, auto-open that branch.
    if keep_selection and prev_index is not None and 0 <= prev_index < len(stages):
        selected_branch = self._dw_branch_key_for_stage(stages[prev_index])
        self._dw_collapsed_set().discard(selected_branch)

    for child in self.stage_list.get_children():
        self.stage_list.remove(child)

    if not stages:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        lbl = Gtk.Label(label="No stages yet.\nUse 'Add Stage' or import a roadmap.")
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_margin_top(16)
        row.add(lbl)
        self.stage_list.add(row)
    else:
        for group in self._dw_branch_groups():
            self.stage_list.add(self._dw_make_branch_header_row(group))

            if group["branch"] in self._dw_collapsed_set():
                continue

            for stage_index in group["indexes"]:
                row = self._make_stage_row(stage_index, stages[stage_index])

                try:
                    child = row.get_child()
                    if child is not None:
                        child.set_margin_start(18)
                except Exception:
                    pass

                self.stage_list.add(row)

    self.stage_list.show_all()
    self._update_overall_progress()

    if keep_selection and prev_index is not None:
        row = self._dw_find_stage_row(prev_index)
        if row is not None:
            self.stage_list.select_row(row)
            return

    first_stage_row = None
    for row in self.stage_list.get_children():
        if hasattr(row, "stage_index"):
            first_stage_row = row
            break

    if first_stage_row is not None:
        self.stage_list.select_row(first_stage_row)
    else:
        self.selected_stage_index = None
        self._set_right_enabled(False)


def _dw_make_stage_row_branch_aware(self, index, stage):
    # Use whatever _make_stage_row implementation existed before this patch.
    row = ChecklistWindow._dw_branch_group_base_make_stage_row(self, index, stage)

    try:
        child = row.get_child()
        if child is not None:
            branch = str(stage.get("branch", "") or "").strip()
            issue = str(stage.get("issue", "") or "").strip()

            tooltip_parts = []
            if branch:
                tooltip_parts.append(f"Branch: {branch}")
            if issue:
                tooltip_parts.append(f"Issue: {issue}")

            done, total = checklists.progress_for_stage(stage)
            tooltip_parts.append(f"Progress: {done}/{total}")

            row.set_tooltip_text("\n".join(tooltip_parts))
    except Exception:
        pass

    return row


def _dw_add_stage_branch_default(self, _):
    dlg = Gtk.Dialog(title="Add Issue / Stage", transient_for=self, flags=0)
    dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                    Gtk.STOCK_OK, Gtk.ResponseType.OK)
    box = dlg.get_content_area()
    box.set_border_width(12)
    box.set_spacing(8)

    branch_lbl = Gtk.Label(label="Branch / workstream:")
    branch_lbl.set_halign(Gtk.Align.START)
    box.pack_start(branch_lbl, False, False, 0)

    branch_entry = Gtk.Entry()
    branch_entry.set_placeholder_text("e.g. feat/checklist-polish")
    try:
        stage = self._current_stage()
        if stage and stage.get("branch"):
            branch_entry.set_text(stage.get("branch", ""))
    except Exception:
        pass
    box.pack_start(branch_entry, False, False, 0)

    title_lbl = Gtk.Label(label="Issue / stage title:")
    title_lbl.set_halign(Gtk.Align.START)
    box.pack_start(title_lbl, False, False, 0)

    entry = Gtk.Entry()
    entry.set_activates_default(True)
    entry.set_placeholder_text("e.g. Fix empty branch stage import")
    box.pack_start(entry, False, False, 0)

    dlg.set_default_response(Gtk.ResponseType.OK)
    dlg.show_all()

    if dlg.run() == Gtk.ResponseType.OK:
        title = entry.get_text().strip()
        branch = branch_entry.get_text().strip()

        if title:
            stage = checklists.new_stage(title)
            stage["issue"] = title
            stage["kind"] = "Issue"
            if branch:
                stage["branch"] = branch

            self.project_data.setdefault("stages", []).append(stage)
            self.selected_stage_index = len(self.project_data["stages"]) - 1
            self._dw_collapsed_set().discard(branch or "No branch")
            self._refresh_stage_list()
            self._mark_dirty()

    dlg.destroy()


def _dw_restore_resume_branch_aware(self):
    try:
        key = self._mc_resume_key()
        store = _mc_resume_store()
        saved = store.get(key)
    except Exception:
        saved = None

    if not saved:
        return False

    stages = self.project_data.get("stages", [])

    if not stages:
        return False

    try:
        stage_index = int(saved.get("stage", 0))
    except Exception:
        stage_index = 0

    stage_index = max(0, min(stage_index, len(stages) - 1))
    branch = self._dw_branch_key_for_stage(stages[stage_index])
    self._dw_collapsed_set().discard(branch)

    row = self._dw_find_stage_row(stage_index)

    if row is None:
        self._refresh_stage_list(keep_selection=False)
        row = self._dw_find_stage_row(stage_index)

    if row is not None:
        try:
            self.stage_list.unselect_all()
        except Exception:
            pass
        self.stage_list.select_row(row)

    try:
        self.selected_stage_index = stage_index
        self.selected_item_index = None
        self._set_right_enabled(True)
        self._refresh_items_list()
        self._refresh_stage_header()
        self._load_notes()
    except Exception:
        pass

    raw_item = saved.get("item", None)

    try:
        item_index = int(raw_item) if raw_item is not None else None
    except Exception:
        item_index = None

    if item_index is not None:
        items = stages[stage_index].get("items", [])
        if items:
            item_index = max(0, min(item_index, len(items) - 1))
            item_row = self.items_list.get_row_at_index(item_index)

            if item_row is not None:
                try:
                    self.items_list.unselect_all()
                except Exception:
                    pass
                self.items_list.select_row(item_row)
                self.selected_item_index = item_index
                self._load_task_description(item_index)

    return False


if not getattr(ChecklistWindow, "_dw_branch_section_sidebar_patch_applied", False):
    ChecklistWindow._dw_branch_group_base_refresh_stage_list = ChecklistWindow._refresh_stage_list
    ChecklistWindow._dw_branch_group_base_make_stage_row = ChecklistWindow._make_stage_row
    ChecklistWindow._dw_branch_group_base_add_stage = ChecklistWindow._add_stage

    ChecklistWindow._dw_prompt_subject = _dw_prompt_subject
    ChecklistWindow._markdown_import_prompt = _dw_markdown_import_prompt_branch_sections

    ChecklistWindow._dw_branch_key_for_stage = _dw_branch_key_for_stage
    ChecklistWindow._dw_branch_groups = _dw_branch_groups
    ChecklistWindow._dw_collapsed_set = _dw_collapsed_set
    ChecklistWindow._dw_make_branch_header_row = _dw_make_branch_header_row
    ChecklistWindow._dw_toggle_branch = _dw_toggle_branch
    ChecklistWindow._dw_find_stage_row = _dw_find_stage_row

    ChecklistWindow._refresh_stage_list = _dw_refresh_stage_list_branch_grouped
    ChecklistWindow._make_stage_row = _dw_make_stage_row_branch_aware
    ChecklistWindow._add_stage = _dw_add_stage_branch_default

    if hasattr(ChecklistWindow, "_mc_restore_resume"):
        ChecklistWindow._mc_restore_resume = _dw_restore_resume_branch_aware

    ChecklistWindow._dw_branch_section_sidebar_patch_applied = True



# ── DevWise branch collapsed click-row UX patch ─────────────────────────────
# Changes:
# - Branch groups start collapsed by default.
# - New branches imported later also start collapsed.
# - No tiny arrow button.
# - Click anywhere on a branch row to open/close it.
# - Right-click a branch for branch actions.
# - If a remembered stage exists, it is restored only after opening that branch.

def _dw_all_branch_keys_v2(self):
    branches = []

    for stage in self.project_data.get("stages", []):
        try:
            branch = self._dw_branch_key_for_stage(stage)
        except Exception:
            branch = str(stage.get("branch", "") or "").strip() or "No branch"

        if branch not in branches:
            branches.append(branch)

    return branches


def _dw_collapsed_set_click_anywhere(self):
    branches = set(self._dw_all_branch_keys_v2())

    if not hasattr(self, "_dw_collapsed_branches"):
        self._dw_collapsed_branches = set(branches)
        self._dw_seen_branches = set(branches)
        return self._dw_collapsed_branches

    if not hasattr(self, "_dw_seen_branches"):
        self._dw_seen_branches = set()

    # Any newly imported branch should start closed by default.
    new_branches = branches - self._dw_seen_branches
    self._dw_collapsed_branches.update(new_branches)
    self._dw_seen_branches.update(new_branches)

    # Drop collapsed keys for deleted branches.
    self._dw_collapsed_branches.intersection_update(branches)

    return self._dw_collapsed_branches


def _dw_branch_stage_indexes_v2(self, branch):
    indexes = []

    for index, stage in enumerate(self.project_data.get("stages", [])):
        try:
            key = self._dw_branch_key_for_stage(stage)
        except Exception:
            key = str(stage.get("branch", "") or "").strip() or "No branch"

        if key == branch:
            indexes.append(index)

    return indexes


def _dw_branch_summary_text_v2(self, branch):
    indexes = self._dw_branch_stage_indexes_v2(branch)
    stages = self.project_data.get("stages", [])

    done_total = 0
    task_total = 0
    incomplete_tasks = 0

    lines = [f"# Branch: {branch}", ""]

    if not indexes:
        lines.append("No issues/stages in this branch yet.")
        return "\n".join(lines)

    for index in indexes:
        stage = stages[index]
        done, total = checklists.progress_for_stage(stage)
        done_total += done
        task_total += total
        incomplete_tasks += max(0, total - done)

        issue = (
            stage.get("issue")
            or stage.get("title")
            or "Untitled"
        )

        if total <= 0:
            status = "EMPTY"
        elif done <= 0:
            status = "NOT STARTED"
        elif done >= total:
            status = "COMPLETE"
        else:
            status = "IN PROGRESS"

        lines.append(f"## {issue}")
        lines.append(f"Status: {status}")
        lines.append(f"Progress: {done} / {total}")
        lines.append("")

        for item in stage.get("items", []):
            if item.get("done"):
                continue

            lines.append(f"- {item.get('text', '')}")
            desc = str(item.get("description", "") or "").strip()
            if desc:
                lines.append(f"  Descript: {desc}")
            lines.append("")

    lines.insert(2, f"Overall: {done_total} / {task_total} complete")
    lines.insert(3, f"Incomplete tasks: {incomplete_tasks}")
    lines.insert(4, "")

    return "\n".join(lines).rstrip() + "\n"


def _dw_make_branch_header_row_click_anywhere(self, group):
    row = Gtk.ListBoxRow()
    row.set_selectable(True)
    row.is_branch_header = True
    row.branch_key = group["branch"]

    collapsed = group["branch"] in self._dw_collapsed_set()

    icon = "📁" if collapsed else "📂"

    if group["total"] <= 0:
        status = "EMPTY"
    elif group["done"] <= 0:
        status = "NOT STARTED"
    elif group["done"] >= group["total"]:
        status = "COMPLETE"
    else:
        status = "IN PROGRESS"

    active = max(0, group["total"] - group["done"])

    box = Gtk.Box(spacing=8)
    box.set_border_width(8)

    title = Gtk.Label()
    title.set_markup(f"<b>{icon} {group['branch']}</b>")
    title.set_halign(Gtk.Align.START)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    box.pack_start(title, True, True, 0)

    summary = Gtk.Label(label=f"{len(group['indexes'])} issue(s) • {active} active • {group['done']}/{group['total']} • {status}")
    summary.set_halign(Gtk.Align.END)
    summary.get_style_context().add_class("stage-progress")
    box.pack_end(summary, False, False, 0)

    row.set_tooltip_text(
        "Click anywhere on this branch row to open/close it.\n"
        "Right-click for branch actions."
    )

    row.add(box)
    return row


def _dw_find_stage_row_v2(self, stage_index):
    for row in self.stage_list.get_children():
        if getattr(row, "stage_index", None) == stage_index:
            return row
    return None


def _dw_select_stage_and_item_v2(self, stage_index, item_index=None):
    stages = self.project_data.get("stages", [])

    if not (0 <= stage_index < len(stages)):
        return False

    row = self._dw_find_stage_row(stage_index)
    if row is None:
        return False

    try:
        self.stage_list.unselect_all()
    except Exception:
        pass

    self.stage_list.select_row(row)

    self.selected_stage_index = stage_index
    self.selected_item_index = None
    self._set_right_enabled(True)
    self._refresh_items_list()
    self._refresh_stage_header()
    self._load_notes()

    if item_index is not None:
        items = stages[stage_index].get("items", [])
        if items:
            item_index = max(0, min(int(item_index), len(items) - 1))
            item_row = self.items_list.get_row_at_index(item_index)

            if item_row is not None:
                try:
                    self.items_list.unselect_all()
                except Exception:
                    pass

                self.items_list.select_row(item_row)
                self.selected_item_index = item_index
                self._load_task_description(item_index)

    return True


def _dw_refresh_stage_list_closed_default(self, keep_selection=True):
    prev_index = self.selected_stage_index
    stages = self.project_data.get("stages", [])

    for child in self.stage_list.get_children():
        self.stage_list.remove(child)

    if not stages:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        lbl = Gtk.Label(label="No stages yet.\nUse 'Add Stage' or import a roadmap.")
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_margin_top(16)
        row.add(lbl)
        self.stage_list.add(row)
    else:
        for group in self._dw_branch_groups():
            self.stage_list.add(self._dw_make_branch_header_row(group))

            if group["branch"] in self._dw_collapsed_set():
                continue

            for stage_index in group["indexes"]:
                row = self._make_stage_row(stage_index, stages[stage_index])

                try:
                    child = row.get_child()
                    if child is not None:
                        child.set_margin_start(18)
                except Exception:
                    pass

                self.stage_list.add(row)

    self.stage_list.show_all()
    self._update_overall_progress()

    # Preserve visible stage selection only. Do not auto-open branches anymore.
    if keep_selection and prev_index is not None:
        row = self._dw_find_stage_row(prev_index)

        if row is not None:
            self.stage_list.select_row(row)
            return

    self.selected_stage_index = None
    self.selected_item_index = None
    self._set_right_enabled(False)


def _dw_store_pending_resume_closed(self):
    try:
        key = self._mc_resume_key()
        saved = _mc_resume_store().get(key)
    except Exception:
        saved = None

    if saved:
        self._dw_pending_resume = saved

    # Keep branches closed on initial open.
    return False


def _dw_try_restore_pending_for_branch(self, branch):
    saved = getattr(self, "_dw_pending_resume", None)

    if not saved:
        return False

    try:
        stage_index = int(saved.get("stage", 0))
    except Exception:
        return False

    stages = self.project_data.get("stages", [])

    if not (0 <= stage_index < len(stages)):
        return False

    try:
        stage_branch = self._dw_branch_key_for_stage(stages[stage_index])
    except Exception:
        stage_branch = str(stages[stage_index].get("branch", "") or "").strip() or "No branch"

    if stage_branch != branch:
        return False

    raw_item = saved.get("item", None)

    try:
        item_index = int(raw_item) if raw_item is not None else None
    except Exception:
        item_index = None

    restored = self._dw_select_stage_and_item_v2(stage_index, item_index)

    if restored:
        self._dw_pending_resume = None

    return restored


def _dw_toggle_branch_click_anywhere(self, branch):
    collapsed = self._dw_collapsed_set()
    opening = branch in collapsed

    if opening:
        collapsed.remove(branch)
    else:
        collapsed.add(branch)

    self._refresh_stage_list(keep_selection=False)

    if opening:
        # Nice extra: if this branch contained the last selected issue, restore it now.
        if not self._dw_try_restore_pending_for_branch(branch):
            # Otherwise just reveal issues without forcing a selection.
            self.selected_stage_index = None
            self.selected_item_index = None
            self._set_right_enabled(False)
    else:
        self.selected_stage_index = None
        self.selected_item_index = None
        self._set_right_enabled(False)


def _dw_on_stage_selected_click_branch(self, listbox, row):
    if row is not None and getattr(row, "is_branch_header", False):
        branch = getattr(row, "branch_key", "No branch")
        self._dw_toggle_branch(branch)

        try:
            listbox.unselect_row(row)
        except Exception:
            pass

        return

    return ChecklistWindow._dw_branch_click_base_on_stage_selected(self, listbox, row)


def _dw_copy_to_clipboard_quiet_v2(self, text, message="Copied."):
    try:
        self._dw_copy_to_clipboard(text, message)
        return
    except Exception:
        pass

    try:
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text or "", -1)
        self._show_info(message)
    except Exception:
        pass


def _dw_branch_context_menu_v2(self, branch, event):
    menu = Gtk.Menu()

    def add(label, cb):
        item = Gtk.MenuItem(label=label)
        item.connect("activate", cb)
        menu.append(item)

    collapsed = branch in self._dw_collapsed_set()

    add("📂 Open branch" if collapsed else "📁 Close branch",
        lambda _: self._dw_toggle_branch(branch))

    add("📋 Copy branch summary",
        lambda _: self._dw_copy_to_clipboard_quiet_v2(
            self._dw_branch_summary_text_v2(branch),
            "Branch summary copied."
        ))

    menu.append(Gtk.SeparatorMenuItem())

    add("📂 Open all branches", lambda _: self._dw_expand_all_branches())
    add("📁 Close all branches", lambda _: self._dw_collapse_all_branches())

    menu.show_all()
    menu.popup_at_pointer(event)


def _dw_expand_all_branches(self):
    self._dw_collapsed_set().clear()
    self._refresh_stage_list(keep_selection=False)


def _dw_collapse_all_branches(self):
    self._dw_collapsed_branches = set(self._dw_all_branch_keys_v2())
    self.selected_stage_index = None
    self.selected_item_index = None
    self._refresh_stage_list(keep_selection=False)


def _dw_on_stage_list_button_press_branch_menu(self, widget, event):
    row = self.stage_list.get_row_at_y(int(event.y))

    if event.button == 3 and row is not None and getattr(row, "is_branch_header", False):
        branch = getattr(row, "branch_key", "No branch")
        self._dw_branch_context_menu_v2(branch, event)
        return True

    return ChecklistWindow._dw_branch_click_base_stage_button_press(self, widget, event)


if not getattr(ChecklistWindow, "_dw_branch_click_anywhere_patch_applied", False):
    ChecklistWindow._dw_branch_click_base_on_stage_selected = ChecklistWindow._on_stage_selected
    ChecklistWindow._dw_branch_click_base_stage_button_press = ChecklistWindow._on_stage_list_button_press

    ChecklistWindow._dw_all_branch_keys_v2 = _dw_all_branch_keys_v2
    ChecklistWindow._dw_collapsed_set = _dw_collapsed_set_click_anywhere
    ChecklistWindow._dw_branch_stage_indexes_v2 = _dw_branch_stage_indexes_v2
    ChecklistWindow._dw_branch_summary_text_v2 = _dw_branch_summary_text_v2
    ChecklistWindow._dw_make_branch_header_row = _dw_make_branch_header_row_click_anywhere
    ChecklistWindow._dw_find_stage_row = _dw_find_stage_row_v2
    ChecklistWindow._dw_select_stage_and_item_v2 = _dw_select_stage_and_item_v2

    ChecklistWindow._refresh_stage_list = _dw_refresh_stage_list_closed_default
    ChecklistWindow._on_stage_selected = _dw_on_stage_selected_click_branch
    ChecklistWindow._on_stage_list_button_press = _dw_on_stage_list_button_press_branch_menu

    ChecklistWindow._dw_toggle_branch = _dw_toggle_branch_click_anywhere
    ChecklistWindow._dw_store_pending_resume_closed = _dw_store_pending_resume_closed
    ChecklistWindow._dw_try_restore_pending_for_branch = _dw_try_restore_pending_for_branch
    ChecklistWindow._dw_copy_to_clipboard_quiet_v2 = _dw_copy_to_clipboard_quiet_v2
    ChecklistWindow._dw_branch_context_menu_v2 = _dw_branch_context_menu_v2
    ChecklistWindow._dw_expand_all_branches = _dw_expand_all_branches
    ChecklistWindow._dw_collapse_all_branches = _dw_collapse_all_branches

    # Override resume so initial checklist opens with branches closed.
    if hasattr(ChecklistWindow, "_mc_restore_resume"):
        ChecklistWindow._mc_restore_resume = _dw_store_pending_resume_closed

    ChecklistWindow._dw_branch_click_anywhere_patch_applied = True



# ── DevWise branch row click + clean icons patch ────────────────────────────
# Fixes:
# - Branches open closed by default.
# - Click anywhere on branch header row to open/close.
# - Branch names no longer collapse to "...".
# - Removes the confusing green leaf metadata icon from issue rows.
# - Uses clean status icons for issue/stage rows.

def _dw_all_branch_keys_clean(self):
    keys = []

    for stage in self.project_data.get("stages", []):
        branch = str(stage.get("branch", "") or "").strip() or "No branch"

        if branch not in keys:
            keys.append(branch)

    return keys


def _dw_collapsed_set_clean(self):
    branches = set(self._dw_all_branch_keys_clean())

    # First load of this checklist window: every branch starts closed.
    if not hasattr(self, "_dw_branch_closed_state_ready"):
        self._dw_collapsed_branches = set(branches)
        self._dw_seen_branch_keys = set(branches)
        self._dw_branch_closed_state_ready = True
        return self._dw_collapsed_branches

    if not hasattr(self, "_dw_collapsed_branches"):
        self._dw_collapsed_branches = set(branches)

    if not hasattr(self, "_dw_seen_branch_keys"):
        self._dw_seen_branch_keys = set()

    # Newly imported branches start closed too.
    new_branches = branches - self._dw_seen_branch_keys
    self._dw_collapsed_branches.update(new_branches)

    self._dw_seen_branch_keys = set(branches)
    self._dw_collapsed_branches.intersection_update(branches)

    return self._dw_collapsed_branches


def _dw_branch_key_clean(self, stage):
    return str(stage.get("branch", "") or "").strip() or "No branch"


def _dw_branch_groups_clean(self):
    groups = []
    lookup = {}

    for index, stage in enumerate(self.project_data.get("stages", [])):
        branch = self._dw_branch_key_clean(stage)

        if branch not in lookup:
            lookup[branch] = {
                "branch": branch,
                "indexes": [],
                "done": 0,
                "total": 0,
            }
            groups.append(lookup[branch])

        done, total = checklists.progress_for_stage(stage)
        lookup[branch]["indexes"].append(index)
        lookup[branch]["done"] += done
        lookup[branch]["total"] += total

    # Own idea: active branches first, completed branches last.
    def sort_key(group):
        total = group["total"]
        done = group["done"]
        complete = total > 0 and done >= total
        no_work = total <= 0
        return (complete, no_work, group["branch"].lower())

    return sorted(groups, key=sort_key)


def _dw_status_label_clean(done, total):
    if total <= 0:
        return "EMPTY"
    if done <= 0:
        return "NOT STARTED"
    if done >= total:
        return "COMPLETE"
    return "IN PROGRESS"


def _dw_status_icon_clean(done, total):
    status = _dw_status_label_clean(done, total)

    return {
        "COMPLETE": "✅",
        "IN PROGRESS": "🟡",
        "NOT STARTED": "🔵",
        "EMPTY": "⚪",
    }.get(status, "⚪")


def _dw_make_branch_header_row_clean(self, group):
    row = Gtk.ListBoxRow()
    row.set_selectable(False)
    row.is_branch_header = True
    row.branch_key = group["branch"]

    collapsed = group["branch"] in self._dw_collapsed_set_clean()
    folder = "📁" if collapsed else "📂"

    done = group["done"]
    total = group["total"]
    active = max(0, total - done)
    status = _dw_status_label_clean(done, total)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    outer.set_border_width(8)

    title = Gtk.Label(label=f"{folder} {group['branch']}")
    title.set_halign(Gtk.Align.START)
    title.set_xalign(0.0)
    title.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    title.get_style_context().add_class("stage-title")
    outer.pack_start(title, False, False, 0)

    summary = Gtk.Label(
        label=f"{len(group['indexes'])} issue(s) • {active} active • {done}/{total} complete • {status}"
    )
    summary.set_halign(Gtk.Align.START)
    summary.set_xalign(0.0)
    summary.set_ellipsize(Pango.EllipsizeMode.END)
    summary.get_style_context().add_class("stage-progress")
    outer.pack_start(summary, False, False, 0)

    row.set_tooltip_text("Click anywhere on this branch row to open/close it.\nRight-click for branch actions.")
    row.add(outer)
    return row


def _dw_make_stage_row_clean_icons(self, index, stage):
    row = Gtk.ListBoxRow()
    row.stage_index = index
    row.get_style_context().add_class("stage-row")

    vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    vbox.set_border_width(8)
    vbox.set_margin_start(18)

    done, total = checklists.progress_for_stage(stage)
    status = _dw_status_label_clean(done, total)
    icon = _dw_status_icon_clean(done, total)

    title_text = stage.get("issue") or stage.get("title") or "Untitled"
    title_lbl = Gtk.Label(label=f"{icon} {title_text}")
    title_lbl.set_halign(Gtk.Align.START)
    title_lbl.set_xalign(0.0)
    title_lbl.set_line_wrap(True)
    title_lbl.get_style_context().add_class("stage-title")
    vbox.pack_start(title_lbl, False, False, 0)

    prog_lbl = Gtk.Label(label=f"{done} / {total} complete • {status}")
    prog_lbl.set_halign(Gtk.Align.START)
    prog_lbl.set_xalign(0.0)
    prog_lbl.get_style_context().add_class("stage-progress")
    vbox.pack_start(prog_lbl, False, False, 0)

    # Replaces the old green leaf line with a subtle plain text cue.
    branch = str(stage.get("branch", "") or "").strip()
    issue = str(stage.get("issue", "") or "").strip()

    if branch or issue:
        meta = Gtk.Label(label=f"↳ {issue or title_text}")
        meta.set_halign(Gtk.Align.START)
        meta.set_xalign(0.0)
        meta.set_ellipsize(Pango.EllipsizeMode.END)
        meta.get_style_context().add_class("stage-progress")
        vbox.pack_start(meta, False, False, 0)

    row.set_tooltip_text(
        f"Branch: {branch or 'No branch'}\n"
        f"Issue: {issue or title_text}\n"
        f"Progress: {done}/{total}\n"
        f"Status: {status}"
    )

    row.add(vbox)
    return row


def _dw_find_stage_row_clean(self, stage_index):
    for row in self.stage_list.get_children():
        if getattr(row, "stage_index", None) == stage_index:
            return row

    return None


def _dw_set_no_stage_selected_clean(self):
    self.selected_stage_index = None
    self.selected_item_index = None
    self._set_right_enabled(False)


def _dw_refresh_stage_list_clean(self, keep_selection=True):
    prev_index = self.selected_stage_index
    stages = self.project_data.get("stages", [])

    for child in self.stage_list.get_children():
        self.stage_list.remove(child)

    if not stages:
        row = Gtk.ListBoxRow()
        row.set_selectable(False)
        lbl = Gtk.Label(label="No stages yet.\nUse 'Add Stage' or import a roadmap.")
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_margin_top(16)
        row.add(lbl)
        self.stage_list.add(row)
    else:
        for group in self._dw_branch_groups_clean():
            self.stage_list.add(self._dw_make_branch_header_row_clean(group))

            if group["branch"] in self._dw_collapsed_set_clean():
                continue

            for stage_index in group["indexes"]:
                self.stage_list.add(self._make_stage_row(stage_index, stages[stage_index]))

    self.stage_list.show_all()
    self._update_overall_progress()

    # Preserve selection only when the selected stage is currently visible.
    if keep_selection and prev_index is not None:
        row = self._dw_find_stage_row_clean(prev_index)

        if row is not None:
            self.stage_list.select_row(row)
            return

    self._dw_set_no_stage_selected_clean()


def _dw_toggle_branch_clean(self, branch):
    collapsed = self._dw_collapsed_set_clean()

    if branch in collapsed:
        collapsed.remove(branch)
    else:
        collapsed.add(branch)

    self._refresh_stage_list(keep_selection=False)


def _dw_branch_summary_clean(self, branch):
    stages = self.project_data.get("stages", [])
    lines = [f"# Branch: {branch}", ""]

    indexes = [
        i for i, stage in enumerate(stages)
        if self._dw_branch_key_clean(stage) == branch
    ]

    if not indexes:
        return f"# Branch: {branch}\n\nNo issues yet.\n"

    total_done = 0
    total_tasks = 0

    for index in indexes:
        stage = stages[index]
        done, total = checklists.progress_for_stage(stage)
        total_done += done
        total_tasks += total

    lines.append(f"Progress: {total_done} / {total_tasks} tasks complete")
    lines.append("")

    for index in indexes:
        stage = stages[index]
        done, total = checklists.progress_for_stage(stage)
        title = stage.get("issue") or stage.get("title") or "Untitled"

        lines.append(f"## Issue: {title}")
        lines.append(f"Status: {_dw_status_label_clean(done, total)}")
        lines.append(f"Progress: {done} / {total} tasks complete")
        lines.append("")

        for item in stage.get("items", []):
            if item.get("done"):
                continue

            lines.append(f"- {item.get('text', '')}")
            lines.append("Done: no")

            desc = str(item.get("description", "") or "").strip()
            if desc:
                lines.append(f"Descript: {desc}")

            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _dw_copy_branch_summary_clean(self, branch):
    text = self._dw_branch_summary_clean(branch)

    try:
        self._dw_copy_to_clipboard(text, "Branch summary copied.")
    except Exception:
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)
        self._show_info("Branch summary copied.")


def _dw_expand_all_branches_clean(self):
    self._dw_collapsed_branches = set()
    self._refresh_stage_list(keep_selection=False)


def _dw_collapse_all_branches_clean(self):
    self._dw_collapsed_branches = set(self._dw_all_branch_keys_clean())
    self._refresh_stage_list(keep_selection=False)


def _dw_branch_context_menu_clean(self, branch, event):
    menu = Gtk.Menu()

    def add(label, cb):
        item = Gtk.MenuItem(label=label)
        item.connect("activate", cb)
        menu.append(item)

    is_closed = branch in self._dw_collapsed_set_clean()

    add("📂 Open branch" if is_closed else "📁 Close branch", lambda _: self._dw_toggle_branch_clean(branch))
    add("📋 Copy active branch summary", lambda _: self._dw_copy_branch_summary_clean(branch))
    menu.append(Gtk.SeparatorMenuItem())
    add("📂 Open all branches", lambda _: self._dw_expand_all_branches_clean())
    add("📁 Close all branches", lambda _: self._dw_collapse_all_branches_clean())

    menu.show_all()
    menu.popup_at_pointer(event)


def _dw_on_stage_list_button_press_clean(self, widget, event):
    row = self.stage_list.get_row_at_y(int(event.y))

    if row is not None and getattr(row, "is_branch_header", False):
        branch = getattr(row, "branch_key", "No branch")

        if event.button == 1:
            self._dw_toggle_branch_clean(branch)
            return True

        if event.button == 3:
            self._dw_branch_context_menu_clean(branch, event)
            return True

    return ChecklistWindow._dw_clean_branch_base_button_press(self, widget, event)


def _dw_on_stage_selected_clean(self, listbox, row):
    # Branch rows are now non-selectable and handled by button-press.
    # This avoids clicking a branch accidentally clearing the main detail pane.
    if row is not None and getattr(row, "is_branch_header", False):
        return

    return ChecklistWindow._dw_clean_branch_base_stage_selected(self, listbox, row)


if not getattr(ChecklistWindow, "_dw_clean_branch_click_patch_applied", False):
    ChecklistWindow._dw_clean_branch_base_button_press = ChecklistWindow._on_stage_list_button_press
    ChecklistWindow._dw_clean_branch_base_stage_selected = ChecklistWindow._on_stage_selected

    ChecklistWindow._dw_all_branch_keys_clean = _dw_all_branch_keys_clean
    ChecklistWindow._dw_collapsed_set_clean = _dw_collapsed_set_clean
    ChecklistWindow._dw_collapsed_set = _dw_collapsed_set_clean
    ChecklistWindow._dw_branch_key_clean = _dw_branch_key_clean
    ChecklistWindow._dw_branch_groups_clean = _dw_branch_groups_clean

    ChecklistWindow._dw_make_branch_header_row_clean = _dw_make_branch_header_row_clean
    ChecklistWindow._dw_make_branch_header_row = _dw_make_branch_header_row_clean
    ChecklistWindow._make_stage_row = _dw_make_stage_row_clean_icons

    ChecklistWindow._dw_find_stage_row_clean = _dw_find_stage_row_clean
    ChecklistWindow._dw_set_no_stage_selected_clean = _dw_set_no_stage_selected_clean
    ChecklistWindow._refresh_stage_list = _dw_refresh_stage_list_clean

    ChecklistWindow._dw_toggle_branch_clean = _dw_toggle_branch_clean
    ChecklistWindow._dw_toggle_branch = _dw_toggle_branch_clean
    ChecklistWindow._dw_branch_summary_clean = _dw_branch_summary_clean
    ChecklistWindow._dw_copy_branch_summary_clean = _dw_copy_branch_summary_clean
    ChecklistWindow._dw_expand_all_branches_clean = _dw_expand_all_branches_clean
    ChecklistWindow._dw_collapse_all_branches_clean = _dw_collapse_all_branches_clean
    ChecklistWindow._dw_branch_context_menu_clean = _dw_branch_context_menu_clean

    ChecklistWindow._on_stage_list_button_press = _dw_on_stage_list_button_press_clean
    ChecklistWindow._on_stage_selected = _dw_on_stage_selected_clean

    ChecklistWindow._dw_clean_branch_click_patch_applied = True



# ── DevWise live branch stats + empty placeholder cleanup patch ─────────────
# Fixes:
# - Branch header stats update immediately when ticking/unticking tasks.
# - Old empty "General" stages from previous imports are removed automatically.
# - Cleanup is persisted so the ghost General row does not come back after restart.
# - Keeps the opened branch open after checkbox toggles.

def _dw_is_empty_placeholder_stage_v3(self, stage):
    title = str(stage.get("title", "") or "").strip().lower()
    issue = str(stage.get("issue", "") or "").strip().lower()
    notes = str(stage.get("notes", "") or "").strip()
    branch_notes = str(stage.get("branch_notes", "") or "").strip()
    items = stage.get("items", []) or []

    placeholder_titles = {
        "",
        "general",
        "untitled",
        "untitled issue",
        "untitled stage",
    }

    return (
        title in placeholder_titles
        and issue in placeholder_titles
        and not items
        and not notes
        and not branch_notes
    )


def _dw_cleanup_empty_placeholder_stages_v3(self, save=True):
    stages = self.project_data.get("stages", [])

    if not stages:
        return 0

    cleaned = []
    removed = 0

    for stage in stages:
        if self._dw_is_empty_placeholder_stage_v3(stage):
            removed += 1
            continue

        cleaned.append(stage)

    if removed:
        self.project_data["stages"] = cleaned

        if self.selected_stage_index is not None:
            self.selected_stage_index = None
            self.selected_item_index = None

        if save:
            try:
                checklists.save_project_data(self.project_path, self.project_data)
            except Exception:
                pass

    return removed


def _dw_find_stage_row_live_v3(self, stage_index):
    for row in self.stage_list.get_children():
        if getattr(row, "stage_index", None) == stage_index:
            return row

    return None


def _dw_reselect_stage_item_v3(self, stage_index, item_index=None):
    stages = self.project_data.get("stages", [])

    if not (0 <= stage_index < len(stages)):
        self.selected_stage_index = None
        self.selected_item_index = None
        self._set_right_enabled(False)
        return

    row = self._dw_find_stage_row_live_v3(stage_index)

    if row is not None:
        try:
            self.stage_list.unselect_all()
        except Exception:
            pass

        self.stage_list.select_row(row)

    self.selected_stage_index = stage_index
    self.selected_item_index = None
    self._set_right_enabled(True)
    self._refresh_items_list()
    self._refresh_stage_header()
    self._load_notes()

    if item_index is not None:
        items = stages[stage_index].get("items", [])

        if items:
            item_index = max(0, min(int(item_index), len(items) - 1))
            item_row = self.items_list.get_row_at_index(item_index)

            if item_row is not None:
                try:
                    self.items_list.unselect_all()
                except Exception:
                    pass

                self.items_list.select_row(item_row)
                self.selected_item_index = item_index
                self._load_task_description(item_index)


def _dw_on_item_toggled_live_branch_stats_v3(self, check, index):
    stage = self._current_stage()

    if stage is None:
        return

    stage_index = self.selected_stage_index
    item_index = index

    items = stage.get("items", [])

    if 0 <= index < len(items):
        items[index]["done"] = check.get_active()

    # Own idea: if the task tick makes this issue complete, keep the issue visible,
    # but refresh the whole left tree so branch active count/status updates instantly.
    try:
        branch = str(stage.get("branch", "") or "").strip() or "No branch"
        if hasattr(self, "_dw_collapsed_branches"):
            self._dw_collapsed_branches.discard(branch)
    except Exception:
        pass

    self._cleanup_empty_placeholder_stages_v3(save=False)

    # Full left-side refresh is intentional here because branch headers are
    # calculated from all child stages.
    self._refresh_stage_list(keep_selection=True)

    if stage_index is not None:
        self._dw_reselect_stage_item_v3(stage_index, item_index)

    self._update_overall_progress()
    self._mark_dirty()


def _dw_init_live_branch_stats_cleanup_v3(self, *args, **kwargs):
    ChecklistWindow._dw_live_branch_stats_base_init(self, *args, **kwargs)

    removed = self._cleanup_empty_placeholder_stages_v3(save=True)

    if removed:
        try:
            self._refresh_stage_list(keep_selection=False)
            self._set_right_enabled(False)
            self._update_overall_progress()
        except Exception:
            pass

        try:
            self.statusbar.push(0, f"Removed {removed} empty placeholder stage(s).")
        except Exception:
            pass


def _dw_refresh_stage_list_with_cleanup_v3(self, keep_selection=True):
    self._cleanup_empty_placeholder_stages_v3(save=False)
    return ChecklistWindow._dw_live_branch_stats_base_refresh_stage_list(self, keep_selection=keep_selection)


def _dw_remove_empty_placeholders_menu_action_v3(self, *_):
    removed = self._cleanup_empty_placeholder_stages_v3(save=True)
    self._refresh_stage_list(keep_selection=False)
    self._set_right_enabled(False)
    self._update_overall_progress()

    if removed:
        self._show_info(f"Removed {removed} empty placeholder stage(s).")
    else:
        self._show_info("No empty placeholder stages found.")


def _dw_on_stage_list_button_press_with_cleanup_menu_v3(self, widget, event):
    # Keep all existing branch/stage right-click behaviour.
    result = ChecklistWindow._dw_live_branch_stats_base_stage_button_press(self, widget, event)

    # Ctrl + right-click empty area = cleanup shortcut.
    try:
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        row = self.stage_list.get_row_at_y(int(event.y))

        if event.button == 3 and ctrl and row is None:
            menu = Gtk.Menu()
            item = Gtk.MenuItem(label="🧹 Remove empty placeholder stages")
            item.connect("activate", self._dw_remove_empty_placeholders_menu_action_v3)
            menu.append(item)
            menu.show_all()
            menu.popup_at_pointer(event)
            return True
    except Exception:
        pass

    return result


if not getattr(ChecklistWindow, "_dw_live_branch_stats_cleanup_patch_applied", False):
    ChecklistWindow._dw_live_branch_stats_base_init = ChecklistWindow.__init__
    ChecklistWindow._dw_live_branch_stats_base_refresh_stage_list = ChecklistWindow._refresh_stage_list
    ChecklistWindow._dw_live_branch_stats_base_stage_button_press = ChecklistWindow._on_stage_list_button_press

    ChecklistWindow._dw_is_empty_placeholder_stage_v3 = _dw_is_empty_placeholder_stage_v3
    ChecklistWindow._cleanup_empty_placeholder_stages_v3 = _dw_cleanup_empty_placeholder_stages_v3
    ChecklistWindow._dw_find_stage_row_live_v3 = _dw_find_stage_row_live_v3
    ChecklistWindow._dw_reselect_stage_item_v3 = _dw_reselect_stage_item_v3
    ChecklistWindow._dw_remove_empty_placeholders_menu_action_v3 = _dw_remove_empty_placeholders_menu_action_v3

    ChecklistWindow.__init__ = _dw_init_live_branch_stats_cleanup_v3
    ChecklistWindow._refresh_stage_list = _dw_refresh_stage_list_with_cleanup_v3
    ChecklistWindow._on_item_toggled = _dw_on_item_toggled_live_branch_stats_v3
    ChecklistWindow._on_stage_list_button_press = _dw_on_stage_list_button_press_with_cleanup_menu_v3

    ChecklistWindow._dw_live_branch_stats_cleanup_patch_applied = True



# ── DevWise quarter-screen checklist fit patch ──────────────────────────────
# Goal:
# - Fit comfortably inside a 1/4 screen tile on 1080p-ish displays.
# - Avoid giant saved geometry making the checklist reopen too large.
# - Reduce minimum widget pressure from toolbar/items/notes/sidebar.
# - Keep this as a small compatibility patch rather than a full UI rewrite.

from gi.repository import Gtk as _DWQGtk, Gdk as _DWQGdk, Pango as _DWQPango, GLib as _DWQGLib


def _dwq_workarea():
    try:
        display = _DWQGdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        area = monitor.get_workarea()
        return int(area.width), int(area.height)
    except Exception:
        try:
            screen = _DWQGdk.Screen.get_default()
            return int(screen.get_width()), int(screen.get_height())
        except Exception:
            return 1920, 1080


def _dwq_target_size():
    width, height = _dwq_workarea()

    # Quarter tile target. Leave a little breathing room for Cinnamon panels,
    # titlebars and gTile borders.
    target_w = max(620, min(920, int(width * 0.48)))
    target_h = max(420, min(520, int(height * 0.48)))

    return target_w, target_h


def _dwq_clamp(value, low, high):
    try:
        value = int(value)
    except Exception:
        value = low

    return max(low, min(high, value))


def _dwq_walk_widgets(widget):
    yield widget

    if isinstance(widget, _DWQGtk.Container):
        try:
            children = widget.get_children()
        except Exception:
            children = []

        for child in children:
            yield from _dwq_walk_widgets(child)


def _dwq_short_button_label(label):
    replacements = {
        "📋 Paste / Import Roadmap": "📋 Import",
        "➕ Add Stage": "➕ Issue",
        "➕ Add Item": "➕ Task",
        "📤 Export": "📤 Export",
        "🗑 Delete All": "🗑 All",
        "🙈 Hide Main Window": "🙈 Hide",
        "👁 Show Main Window": "👁 Main",
        "📌 Always on Top": "📌 Top",
        "Create Issue From Selected": "Issue",
        "Create/Switch Branch": "Branch",
        "🗑 Remove Selected Stage": "🗑 Issue",
        "🗑 Remove Selected Item": "🗑 Task",
    }

    return replacements.get(label, label)


def _dwq_apply_compact_widget_rules(self):
    target_w, target_h = _dwq_target_size()

    try:
        self.set_resizable(True)
        self.set_default_size(target_w, target_h)
        self.set_size_request(420, 300)
    except Exception:
        pass

    for widget in _dwq_walk_widgets(self):
        try:
            widget.set_hexpand(True)
            widget.set_vexpand(False)
        except Exception:
            pass

        if isinstance(widget, _DWQGtk.Button):
            try:
                label = widget.get_label()
                if label:
                    widget.set_label(_dwq_short_button_label(label))
            except Exception:
                pass

            try:
                widget.set_size_request(1, -1)
            except Exception:
                pass

        elif isinstance(widget, _DWQGtk.Label):
            try:
                raw = widget.get_text() or ""

                if len(raw) > 18:
                    widget.set_max_width_chars(24)
                    widget.set_ellipsize(_DWQPango.EllipsizeMode.MIDDLE)
                    widget.set_single_line_mode(True)

                widget.set_line_wrap(False)
            except Exception:
                pass

        elif isinstance(widget, _DWQGtk.ScrolledWindow):
            try:
                widget.set_policy(_DWQGtk.PolicyType.AUTOMATIC, _DWQGtk.PolicyType.AUTOMATIC)
            except Exception:
                pass

            try:
                widget.set_min_content_width(1)
            except Exception:
                pass

            try:
                widget.set_min_content_height(60)
            except Exception:
                pass

        elif isinstance(widget, _DWQGtk.Paned):
            try:
                if widget.get_orientation() == _DWQGtk.Orientation.HORIZONTAL:
                    widget.set_position(190)
            except Exception:
                pass

        elif isinstance(widget, _DWQGtk.TextView):
            try:
                widget.set_size_request(1, 55)
            except Exception:
                pass

        elif isinstance(widget, _DWQGtk.ListBox):
            try:
                widget.set_size_request(1, 80)
            except Exception:
                pass

    # Known checklist widgets.
    for attr, req in [
        ("stage_list", (150, 90)),
        ("items_list", (220, 110)),
        ("notes_view", (220, 55)),
    ]:
        try:
            getattr(self, attr).set_size_request(*req)
        except Exception:
            pass


def _dwq_restore_window_geometry(self):
    target_w, target_h = _dwq_target_size()

    try:
        geom = settings.get("checklist_window_geometry") or {}

        width = _dwq_clamp(geom.get("width", target_w), 420, target_w)
        height = _dwq_clamp(geom.get("height", target_h), 300, target_h)

        self.set_default_size(width, height)
        self.set_size_request(420, 300)

        x = geom.get("x")
        y = geom.get("y")

        if x is not None and y is not None:
            try:
                self.move(int(x), int(y))
            except Exception:
                pass

    except Exception:
        self.set_default_size(target_w, target_h)
        self.set_size_request(420, 300)


def _dwq_save_window_geometry(self):
    try:
        x, y = self.get_position()
        width, height = self.get_size()
        target_w, target_h = _dwq_target_size()

        settings.set_value("checklist_window_geometry", {
            "x": int(x),
            "y": int(y),
            "width": int(_dwq_clamp(width, 420, target_w)),
            "height": int(_dwq_clamp(height, 300, target_h)),
        })
    except Exception:
        pass


def _dwq_on_toggle_main_window(self, btn):
    result = ChecklistWindow._dwq_base_toggle_main_window(self, btn)

    try:
        if btn.get_active():
            btn.set_label("👁 Main")
        else:
            btn.set_label("🙈 Hide")
    except Exception:
        pass

    return result


def _dwq_init(self, *args, **kwargs):
    ChecklistWindow._dwq_base_init(self, *args, **kwargs)

    _dwq_apply_compact_widget_rules(self)

    try:
        w, h = _dwq_target_size()
        self.resize(w, h)
    except Exception:
        pass

    # Re-apply after GTK finishes layout, because some existing patches build
    # branch/issue rows after initial window creation.
    _DWQGLib.idle_add(lambda: (_dwq_apply_compact_widget_rules(self), False)[1])


if not getattr(ChecklistWindow, "_dw_quarter_screen_fit_patch_applied", False):
    ChecklistWindow._dwq_base_init = ChecklistWindow.__init__
    ChecklistWindow._dwq_base_restore_window_geometry = ChecklistWindow._restore_window_geometry
    ChecklistWindow._dwq_base_save_window_geometry = ChecklistWindow._save_window_geometry

    if hasattr(ChecklistWindow, "_on_toggle_main_window"):
        ChecklistWindow._dwq_base_toggle_main_window = ChecklistWindow._on_toggle_main_window
        ChecklistWindow._on_toggle_main_window = _dwq_on_toggle_main_window

    ChecklistWindow._restore_window_geometry = _dwq_restore_window_geometry
    ChecklistWindow._save_window_geometry = _dwq_save_window_geometry
    ChecklistWindow.__init__ = _dwq_init
    ChecklistWindow._dw_quarter_screen_fit_patch_applied = True



# ── DevWise GitHub issue clipboard handoff patch ────────────────────────────
# Adds GitHub-ready title/body copy buttons to the Create Local Issue flow.
# Keeps local DevWise issue creation, but makes GitHub copy/paste fast.

def _dwgh_clipboard(self, text, message="Copied."):
    try:
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text or "", -1)
    except Exception:
        pass

    try:
        self._show_info(message)
    except Exception:
        pass


def _dwgh_buffer_text(buf):
    try:
        start, end = buf.get_bounds()
        return buf.get_text(start, end, False)
    except Exception:
        return ""


def _dwgh_task_lines(tasks):
    lines = []

    for task in tasks or []:
        title = str(task.get("text", "") or "").strip()
        desc = str(task.get("description", "") or "").strip()
        done = bool(task.get("done"))

        if not title:
            continue

        box = "x" if done else " "
        lines.append(f"- [{box}] {title}")

        if desc:
            for line in desc.splitlines():
                line = line.strip()
                if line:
                    lines.append(f"  - {line}")

    return lines


def _dwgh_build_body(self, title, branch, stage, tasks):
    stage_title = str(stage.get("title", "") or "").strip()
    issue_title = str(stage.get("issue", "") or "").strip()
    notes = str(stage.get("notes", "") or "").strip()

    lines = [
        "## Summary",
        "",
        title.strip() or stage_title or issue_title or "New issue",
        "",
        "## Branch",
        "",
        f"`{branch or 'main'}`",
        "",
    ]

    if stage_title and stage_title != title:
        lines.extend([
            "## Source checklist stage",
            "",
            stage_title,
            "",
        ])

    if notes:
        lines.extend([
            "## Notes",
            "",
            notes,
            "",
        ])

    lines.extend([
        "## Tasks",
        "",
    ])

    task_lines = _dwgh_task_lines(tasks)

    if task_lines:
        lines.extend(task_lines)
    else:
        lines.append("- [ ] Add implementation details")

    lines.extend([
        "",
        "## Testing",
        "",
        "- [ ] Run DevWise from terminal",
        "- [ ] Re-test the related checklist workflow",
        "- [ ] Confirm the change is committed and pushed",
    ])

    return "\n".join(lines).rstrip() + "\n"


def _dwgh_copy_title(self, entry, *_):
    title = entry.get_text().strip()
    self._dwgh_clipboard(title, "GitHub issue title copied.")


def _dwgh_copy_body(self, body_buf, *_):
    body = _dwgh_buffer_text(body_buf).strip()
    self._dwgh_clipboard(body, "GitHub issue body copied.")


def _dwgh_copy_both(self, entry, body_buf, *_):
    title = entry.get_text().strip()
    body = _dwgh_buffer_text(body_buf).strip()

    combined = (
        "GitHub issue title:\n"
        f"{title}\n\n"
        "GitHub issue body:\n"
        f"{body}\n"
    )

    self._dwgh_clipboard(combined, "GitHub issue title + body copied.")


def _dwgh_refresh_body_from_title(self, entry, body_buf, branch, stage, tasks):
    # Only auto-refresh while the body has not been manually edited.
    if getattr(self, "_dwgh_body_edited", False):
        return

    title = entry.get_text().strip()
    body_buf.set_text(self._dwgh_build_body(title, branch, stage, tasks))


def _dwgh_mark_body_edited(self, *_):
    self._dwgh_body_edited = True


def _dw_create_issue_from_selected_github_clipboard(self, _=None):
    if not dw_issues:
        self._show_info("Issue helper is unavailable.")
        return

    stage = self._current_stage()

    if stage is None:
        self._show_info("Select an issue/stage first.")
        return

    tasks = self._dw_issue_tasks_from_selection()
    default_title = stage.get("issue") or stage.get("title", "New issue")
    default_branch = stage.get("branch") or dw_issues.slugify(default_title)

    self._dwgh_body_edited = False

    dlg = Gtk.Dialog(title="Create Local Issue / GitHub Copy", transient_for=self, flags=0)
    dlg.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, "Create Issue", Gtk.ResponseType.OK)
    dlg.set_default_size(720, 520)

    box = dlg.get_content_area()
    box.set_border_width(12)
    box.set_spacing(8)

    title_lbl = Gtk.Label()
    title_lbl.set_markup("<b>GitHub issue title:</b>")
    title_lbl.set_halign(Gtk.Align.START)
    box.pack_start(title_lbl, False, False, 0)

    entry = Gtk.Entry()
    entry.set_text(default_title)
    entry.set_activates_default(True)
    box.pack_start(entry, False, False, 0)

    meta = Gtk.Label(label=f"Branch: {default_branch}  •  Tasks captured: {len(tasks)}")
    meta.set_halign(Gtk.Align.START)
    try:
        meta.get_style_context().add_class("stage-progress")
    except Exception:
        pass
    box.pack_start(meta, False, False, 0)

    body_lbl = Gtk.Label()
    body_lbl.set_markup("<b>GitHub issue body / description:</b>")
    body_lbl.set_halign(Gtk.Align.START)
    box.pack_start(body_lbl, False, False, 0)

    body_scroll = Gtk.ScrolledWindow()
    body_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    body_scroll.set_min_content_height(260)

    body_view = Gtk.TextView()
    body_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    body_view.set_monospace(True)
    body_buf = body_view.get_buffer()
    body_buf.set_text(self._dwgh_build_body(default_title, default_branch, stage, tasks))
    body_buf.connect("changed", self._dwgh_mark_body_edited)

    body_scroll.add(body_view)
    box.pack_start(body_scroll, True, True, 0)

    copy_row = Gtk.Box(spacing=6)

    copy_title_btn = Gtk.Button(label="📋 Copy Title")
    copy_title_btn.set_tooltip_text("Copy only the GitHub issue title")
    copy_title_btn.connect("clicked", self._dwgh_copy_title, entry)
    copy_row.pack_start(copy_title_btn, False, False, 0)

    copy_body_btn = Gtk.Button(label="📋 Copy Body")
    copy_body_btn.set_tooltip_text("Copy only the GitHub issue body/description")
    copy_body_btn.connect("clicked", self._dwgh_copy_body, body_buf)
    copy_row.pack_start(copy_body_btn, False, False, 0)

    copy_both_btn = Gtk.Button(label="📋 Copy Both")
    copy_both_btn.set_tooltip_text("Copy title and body together")
    copy_both_btn.connect("clicked", self._dwgh_copy_both, entry, body_buf)
    copy_row.pack_start(copy_both_btn, False, False, 0)

    hint = Gtk.Label(label="Paste Title into GitHub title, then Body into GitHub description.")
    hint.set_halign(Gtk.Align.START)
    try:
        hint.get_style_context().add_class("stage-progress")
    except Exception:
        pass
    copy_row.pack_start(hint, True, True, 0)

    box.pack_start(copy_row, False, False, 0)

    entry.connect("changed", self._dwgh_refresh_body_from_title, body_buf, default_branch, stage, tasks)

    dlg.set_default_response(Gtk.ResponseType.OK)
    dlg.show_all()

    response = dlg.run()
    title = entry.get_text().strip()
    body = _dwgh_buffer_text(body_buf).strip()
    dlg.destroy()

    if response != Gtk.ResponseType.OK or not title:
        return

    branch = stage.get("branch") or dw_issues.slugify(title)
    issue = dw_issues.create_issue(
        self.project_path,
        title,
        branch=branch,
        tasks=tasks,
        source="checklist",
    )

    self.project_data["active_issue_id"] = issue.get("id")
    stage["issue_id"] = issue.get("id")
    stage["issue"] = issue.get("title")
    stage["branch"] = issue.get("branch")

    for item in stage.get("items", []):
        for task in tasks:
            if item.get("text") == task.get("text"):
                item["issue_id"] = issue.get("id")

    self._dw_refresh_issue_combo()
    self._dw_update_branch_issue_bar()
    self._refresh_stage_header()
    self._refresh_stage_list()
    self._mark_dirty()

    combined = (
        "GitHub issue title:\n"
        f"{title}\n\n"
        "GitHub issue body:\n"
        f"{body}\n"
    )
    self._dwgh_clipboard(
        combined,
        "Created local issue and copied GitHub title + body.\n\nPaste into GitHub issue fields.",
    )


if not getattr(ChecklistWindow, "_dw_github_issue_clipboard_patch_applied", False):
    ChecklistWindow._dwgh_clipboard = _dwgh_clipboard
    ChecklistWindow._dwgh_build_body = _dwgh_build_body
    ChecklistWindow._dwgh_copy_title = _dwgh_copy_title
    ChecklistWindow._dwgh_copy_body = _dwgh_copy_body
    ChecklistWindow._dwgh_copy_both = _dwgh_copy_both
    ChecklistWindow._dwgh_refresh_body_from_title = _dwgh_refresh_body_from_title
    ChecklistWindow._dwgh_mark_body_edited = _dwgh_mark_body_edited

    ChecklistWindow._dw_create_issue_from_selected = _dw_create_issue_from_selected_github_clipboard
    ChecklistWindow._dw_github_issue_clipboard_patch_applied = True



# ── DevWise standalone GitHub issue handoff window patch ────────────────────
# Makes the GitHub/local issue handoff a standalone Gtk.Window instead of a
# transient/modal dialog. This lets the checklist window be hidden/minimised
# while the issue title/body window stays visible for GitHub copy/paste.

def _dwgh_get_body_text_v2(buf):
    try:
        start, end = buf.get_bounds()
        return buf.get_text(start, end, False)
    except Exception:
        return ""


def _dwgh_keep_issue_window_ref(self, win):
    if not hasattr(self, "_dw_issue_handoff_windows"):
        self._dw_issue_handoff_windows = []

    self._dw_issue_handoff_windows.append(win)

    def _drop_ref(_win):
        try:
            self._dw_issue_handoff_windows.remove(_win)
        except Exception:
            pass

    win.connect("destroy", _drop_ref)


def _dwgh_copy_title_v2(self, entry, status_lbl=None):
    title = entry.get_text().strip()

    try:
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(title, -1)
    except Exception:
        pass

    if status_lbl is not None:
        status_lbl.set_text("✅ Title copied")


def _dwgh_copy_body_v2(self, body_buf, status_lbl=None):
    body = _dwgh_get_body_text_v2(body_buf).strip()

    try:
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(body, -1)
    except Exception:
        pass

    if status_lbl is not None:
        status_lbl.set_text("✅ Body copied")


def _dwgh_copy_both_v2(self, entry, body_buf, status_lbl=None):
    title = entry.get_text().strip()
    body = _dwgh_get_body_text_v2(body_buf).strip()

    combined = (
        "GitHub issue title:\n"
        f"{title}\n\n"
        "GitHub issue body:\n"
        f"{body}\n"
    )

    try:
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(combined, -1)
    except Exception:
        pass

    if status_lbl is not None:
        status_lbl.set_text("✅ Title + body copied")


def _dwgh_create_local_issue_from_window_v2(self, win, entry, body_buf, branch, stage, tasks, status_lbl=None):
    if not dw_issues:
        if status_lbl is not None:
            status_lbl.set_text("❌ Issue helper unavailable")
        return

    title = entry.get_text().strip()
    body = _dwgh_get_body_text_v2(body_buf).strip()

    if not title:
        if status_lbl is not None:
            status_lbl.set_text("❌ Add an issue title first")
        return

    issue_branch = stage.get("branch") or branch or dw_issues.slugify(title)

    issue = dw_issues.create_issue(
        self.project_path,
        title,
        branch=issue_branch,
        tasks=tasks,
        source="checklist",
    )

    self.project_data["active_issue_id"] = issue.get("id")
    stage["issue_id"] = issue.get("id")
    stage["issue"] = issue.get("title")
    stage["branch"] = issue.get("branch")

    for item in stage.get("items", []):
        for task in tasks:
            if item.get("text") == task.get("text"):
                item["issue_id"] = issue.get("id")

    try:
        self._dw_refresh_issue_combo()
    except Exception:
        pass

    try:
        self._dw_update_branch_issue_bar()
    except Exception:
        pass

    try:
        self._refresh_stage_header()
        self._refresh_stage_list()
        self._mark_dirty()
    except Exception:
        pass

    combined = (
        "GitHub issue title:\n"
        f"{title}\n\n"
        "GitHub issue body:\n"
        f"{body}\n"
    )

    try:
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(combined, -1)
    except Exception:
        pass

    if status_lbl is not None:
        status_lbl.set_text("✅ Local issue created + title/body copied")

    try:
        win.set_title("✅ Issue Handoff — Created")
    except Exception:
        pass


def _dwgh_hide_checklist_from_issue_window_v2(self, win=None):
    try:
        self.hide()
    except Exception:
        pass


def _dwgh_show_checklist_from_issue_window_v2(self, win=None):
    try:
        self.show()
        self.present()
    except Exception:
        pass


def _dwgh_open_github_new_issue_v2(self, status_lbl=None):
    import subprocess

    candidates = []

    try:
        ok, out = checklists.git_ops.run_custom(self.project_path, "git remote get-url origin")
        if ok and out:
            candidates.append(out.strip())
    except Exception:
        pass

    try:
        from core import git_ops
        ok, out = git_ops.run_custom(self.project_path, "git remote get-url origin")
        if ok and out:
            candidates.append(out.strip())
    except Exception:
        pass

    url = ""

    for remote in candidates:
        r = remote.strip()

        if r.startswith("git@github.com:"):
            repo = r.replace("git@github.com:", "", 1).removesuffix(".git")
            url = f"https://github.com/{repo}/issues/new"
            break

        if "github.com" in r:
            repo = r.replace("https://github.com/", "").replace("http://github.com/", "").removesuffix(".git").strip("/")
            if repo:
                url = f"https://github.com/{repo}/issues/new"
                break

    if not url:
        url = "https://github.com/issues"

    try:
        subprocess.Popen(["xdg-open", url])
        if status_lbl is not None:
            status_lbl.set_text("🌐 Opened GitHub issues page")
    except Exception:
        if status_lbl is not None:
            status_lbl.set_text("❌ Could not open browser")


def _dw_create_issue_from_selected_standalone_handoff(self, _=None):
    if not dw_issues:
        self._show_info("Issue helper is unavailable.")
        return

    stage = self._current_stage()

    if stage is None:
        self._show_info("Select an issue/stage first.")
        return

    tasks = self._dw_issue_tasks_from_selection()
    default_title = stage.get("issue") or stage.get("title", "New issue")
    default_branch = stage.get("branch") or dw_issues.slugify(default_title)

    win = Gtk.Window(title="GitHub Issue Handoff")
    win.set_default_size(740, 560)
    win.set_size_request(460, 330)
    win.set_resizable(True)
    win.set_keep_above(True)

    try:
        win.set_type_hint(Gdk.WindowTypeHint.UTILITY)
    except Exception:
        pass

    self._dwgh_keep_issue_window_ref(win)

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    root.set_border_width(12)
    win.add(root)

    header = Gtk.Box(spacing=8)

    title_lbl = Gtk.Label()
    title_lbl.set_markup("<b>GitHub Issue Handoff</b>")
    title_lbl.set_halign(Gtk.Align.START)
    header.pack_start(title_lbl, True, True, 0)

    hide_checklist_btn = Gtk.Button(label="🙈 Hide Checklist")
    hide_checklist_btn.set_tooltip_text("Hide the checklist while keeping this issue window open")
    hide_checklist_btn.connect("clicked", lambda *_: self._dwgh_hide_checklist_from_issue_window_v2(win))
    header.pack_end(hide_checklist_btn, False, False, 0)

    show_checklist_btn = Gtk.Button(label="👁 Checklist")
    show_checklist_btn.set_tooltip_text("Show the checklist again")
    show_checklist_btn.connect("clicked", lambda *_: self._dwgh_show_checklist_from_issue_window_v2(win))
    header.pack_end(show_checklist_btn, False, False, 0)

    root.pack_start(header, False, False, 0)

    root.pack_start(Gtk.Separator(), False, False, 0)

    title_label = Gtk.Label(label="GitHub issue title:")
    title_label.set_halign(Gtk.Align.START)
    root.pack_start(title_label, False, False, 0)

    entry = Gtk.Entry()
    entry.set_text(default_title)
    root.pack_start(entry, False, False, 0)

    meta = Gtk.Label(label=f"Branch: {default_branch}  •  Tasks captured: {len(tasks)}")
    meta.set_halign(Gtk.Align.START)
    try:
        meta.get_style_context().add_class("stage-progress")
    except Exception:
        pass
    root.pack_start(meta, False, False, 0)

    body_label = Gtk.Label(label="GitHub issue body / description:")
    body_label.set_halign(Gtk.Align.START)
    root.pack_start(body_label, False, False, 0)

    body_scroll = Gtk.ScrolledWindow()
    body_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    body_scroll.set_min_content_height(260)

    body_view = Gtk.TextView()
    body_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    body_view.set_monospace(True)

    body_buf = body_view.get_buffer()
    body_buf.set_text(self._dwgh_build_body(default_title, default_branch, stage, tasks))

    body_scroll.add(body_view)
    root.pack_start(body_scroll, True, True, 0)

    status_lbl = Gtk.Label(label="Ready — copy title/body into GitHub.")
    status_lbl.set_halign(Gtk.Align.START)
    try:
        status_lbl.get_style_context().add_class("stage-progress")
    except Exception:
        pass

    btn_row = Gtk.Box(spacing=6)

    copy_title_btn = Gtk.Button(label="📋 Title")
    copy_title_btn.connect("clicked", lambda *_: self._dwgh_copy_title_v2(entry, status_lbl))
    btn_row.pack_start(copy_title_btn, False, False, 0)

    copy_body_btn = Gtk.Button(label="📋 Body")
    copy_body_btn.connect("clicked", lambda *_: self._dwgh_copy_body_v2(body_buf, status_lbl))
    btn_row.pack_start(copy_body_btn, False, False, 0)

    copy_both_btn = Gtk.Button(label="📋 Both")
    copy_both_btn.connect("clicked", lambda *_: self._dwgh_copy_both_v2(entry, body_buf, status_lbl))
    btn_row.pack_start(copy_both_btn, False, False, 0)

    open_github_btn = Gtk.Button(label="🌐 GitHub")
    open_github_btn.set_tooltip_text("Open the GitHub new issue page for this repo when possible")
    open_github_btn.connect("clicked", lambda *_: self._dwgh_open_github_new_issue_v2(status_lbl))
    btn_row.pack_start(open_github_btn, False, False, 0)

    create_btn = Gtk.Button(label="Create Local Issue")
    create_btn.connect(
        "clicked",
        lambda *_: self._dwgh_create_local_issue_from_window_v2(
            win, entry, body_buf, default_branch, stage, tasks, status_lbl
        )
    )
    btn_row.pack_end(create_btn, False, False, 0)

    close_btn = Gtk.Button(label="Close")
    close_btn.connect("clicked", lambda *_: win.destroy())
    btn_row.pack_end(close_btn, False, False, 0)

    root.pack_start(btn_row, False, False, 0)
    root.pack_start(status_lbl, False, False, 0)

    def _refresh_body_from_title(_entry):
        try:
            current_body = _dwgh_get_body_text_v2(body_buf).strip()
            generated_old = self._dwgh_build_body(default_title, default_branch, stage, tasks).strip()

            # Only auto-refresh if user has not manually changed the body.
            if current_body == generated_old or not current_body:
                body_buf.set_text(self._dwgh_build_body(entry.get_text().strip(), default_branch, stage, tasks))
        except Exception:
            pass

    entry.connect("changed", _refresh_body_from_title)

    win.show_all()
    win.present()


if not getattr(ChecklistWindow, "_dw_standalone_issue_handoff_patch_applied", False):
    ChecklistWindow._dwgh_keep_issue_window_ref = _dwgh_keep_issue_window_ref
    ChecklistWindow._dwgh_copy_title_v2 = _dwgh_copy_title_v2
    ChecklistWindow._dwgh_copy_body_v2 = _dwgh_copy_body_v2
    ChecklistWindow._dwgh_copy_both_v2 = _dwgh_copy_both_v2
    ChecklistWindow._dwgh_create_local_issue_from_window_v2 = _dwgh_create_local_issue_from_window_v2
    ChecklistWindow._dwgh_hide_checklist_from_issue_window_v2 = _dwgh_hide_checklist_from_issue_window_v2
    ChecklistWindow._dwgh_show_checklist_from_issue_window_v2 = _dwgh_show_checklist_from_issue_window_v2
    ChecklistWindow._dwgh_open_github_new_issue_v2 = _dwgh_open_github_new_issue_v2

    ChecklistWindow._dw_create_issue_from_selected = _dw_create_issue_from_selected_standalone_handoff
    ChecklistWindow._dw_standalone_issue_handoff_patch_applied = True



# ── DevWise branch handoff window patch ─────────────────────────────────────
# Behaviour:
# - Click a checklist branch/folder row, then press Branch.
# - Branch opens a standalone handoff window instead of only create/switch.
# - Window shows copyable branch name.
# - Window shows copyable full checklist description for that branch.
# - Checklist task completion is exported as GitHub-style [x] / [ ] ticks.
# - Includes a safe Create/Switch Git Branch button inside the handoff window.

def _dwbh_copy_text(self, text, status_lbl=None, message="Copied."):
    try:
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text or "", -1)
    except Exception:
        pass

    if status_lbl is not None:
        try:
            status_lbl.set_text("✅ " + message)
            return
        except Exception:
            pass

    try:
        self._show_info(message)
    except Exception:
        pass


def _dwbh_buffer_text(buf):
    try:
        start, end = buf.get_bounds()
        return buf.get_text(start, end, False)
    except Exception:
        return ""


def _dwbh_stage_branch(self, stage):
    return str(stage.get("branch", "") or "").strip() or "No branch"


def _dwbh_selected_branch(self):
    branch = str(getattr(self, "_dw_selected_branch_key", "") or "").strip()

    if branch and branch != "No branch":
        return branch

    stage = None

    try:
        stage = self._current_stage()
    except Exception:
        stage = None

    if stage and str(stage.get("branch", "") or "").strip():
        return str(stage.get("branch", "") or "").strip()

    try:
        issue = self._dw_current_issue()
        if issue and issue.get("branch"):
            return str(issue.get("branch", "")).strip()
    except Exception:
        pass

    try:
        current = self._dw_current_branch()
        if current:
            return str(current).strip()
    except Exception:
        pass

    return ""


def _dwbh_progress_status(done, total):
    if total <= 0:
        return "EMPTY"
    if done <= 0:
        return "NOT STARTED"
    if done >= total:
        return "COMPLETE"
    return "IN PROGRESS"


def _dwbh_branch_stages(self, branch):
    stages = []

    for stage in self.project_data.get("stages", []):
        if self._dwbh_stage_branch(stage) == branch:
            stages.append(stage)

    return stages


def _dwbh_build_branch_description(self, branch):
    stages = self._dwbh_branch_stages(branch)

    total_done = 0
    total_tasks = 0

    for stage in stages:
        done, total = checklists.progress_for_stage(stage)
        total_done += done
        total_tasks += total

    overall_status = _dwbh_progress_status(total_done, total_tasks)

    lines = [
        f"# Branch: {branch}",
        "",
        f"Status: {overall_status}",
        f"Progress: {total_done} / {total_tasks} tasks complete",
        f"Issues: {len(stages)}",
        "",
        "## Checklist description",
        "",
    ]

    if not stages:
        lines.extend([
            "No checklist issues were found for this branch yet.",
            "",
            "## Tasks",
            "",
            "- [ ] Add checklist issues/tasks for this branch",
        ])
        return "\n".join(lines).rstrip() + "\n"

    for stage in stages:
        title = (
            str(stage.get("issue", "") or "").strip()
            or str(stage.get("title", "") or "").strip()
            or "Untitled issue"
        )

        done, total = checklists.progress_for_stage(stage)
        status = _dwbh_progress_status(done, total)
        notes = str(stage.get("notes", "") or "").strip()
        branch_notes = str(stage.get("branch_notes", "") or "").strip()

        lines.extend([
            f"## Issue: {title}",
            "",
            f"Status: {status}",
            f"Progress: {done} / {total} tasks complete",
            "",
        ])

        if branch_notes:
            lines.extend([
                "Branch notes:",
                branch_notes,
                "",
            ])

        if notes:
            lines.extend([
                "Issue notes:",
                notes,
                "",
            ])

        items = stage.get("items", []) or []

        if not items:
            lines.extend([
                "- [ ] Add implementation task",
                "",
            ])
            continue

        for item in items:
            task = str(item.get("text", "") or "").strip()

            if not task:
                continue

            tick = "x" if item.get("done") else " "
            lines.append(f"- [{tick}] {task}")

            desc = str(item.get("description", "") or "").strip()
            if desc:
                for desc_line in desc.splitlines():
                    desc_line = desc_line.strip()
                    if desc_line:
                        lines.append(f"  - {desc_line}")

        lines.append("")

    lines.extend([
        "## Testing checklist",
        "",
        "- [ ] Run the project from terminal",
        "- [ ] Confirm the branch checklist tasks match the implementation",
        "- [ ] Commit and push the related changes",
        "",
    ])

    return "\n".join(lines).rstrip() + "\n"


def _dwbh_create_or_switch_git_branch(self, branch, status_lbl=None):
    if not branch or branch == "No branch":
        if status_lbl is not None:
            status_lbl.set_text("❌ No branch selected")
        return

    if not dw_git_ops:
        if status_lbl is not None:
            status_lbl.set_text("❌ Git helper unavailable")
        else:
            self._show_info("Git helper unavailable.")
        return

    try:
        q = shlex.quote(branch) if shlex else branch
        ok, existing = dw_git_ops.run_custom(self.project_path, f"git branch --list {q}")

        if ok and existing.strip():
            ok2, out = dw_git_ops.run_custom(self.project_path, f"git checkout {q}")
        else:
            ok2, out = dw_git_ops.run_custom(self.project_path, f"git checkout -b {q}")

        try:
            self._dw_update_branch_issue_bar()
        except Exception:
            pass

        if status_lbl is not None:
            if ok2:
                status_lbl.set_text(f"✅ Now on branch: {branch}")
            else:
                status_lbl.set_text("❌ " + (out or "Could not create/switch branch"))
        else:
            self._show_info(f"Now on branch:\n{branch}" if ok2 else out, title="Branch")
    except Exception as e:
        if status_lbl is not None:
            status_lbl.set_text(f"❌ Branch switch failed: {e}")
        else:
            self._show_info(str(e), title="Branch error")


def _dwbh_open_window(self, branch):
    if not branch:
        self._show_info("Click a checklist branch/folder row first, then press Branch.")
        return

    win = Gtk.Window(title="Branch Handoff")
    win.set_default_size(760, 560)
    win.set_size_request(460, 340)
    win.set_resizable(True)
    win.set_keep_above(True)

    try:
        win.set_type_hint(Gdk.WindowTypeHint.UTILITY)
    except Exception:
        pass

    if not hasattr(self, "_dw_branch_handoff_windows"):
        self._dw_branch_handoff_windows = []

    self._dw_branch_handoff_windows.append(win)

    def _drop_ref(_win):
        try:
            self._dw_branch_handoff_windows.remove(_win)
        except Exception:
            pass

    win.connect("destroy", _drop_ref)

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    root.set_border_width(12)
    win.add(root)

    header = Gtk.Box(spacing=8)

    heading = Gtk.Label()
    heading.set_markup("<b>Branch Handoff</b>")
    heading.set_halign(Gtk.Align.START)
    header.pack_start(heading, True, True, 0)

    hide_btn = Gtk.Button(label="🙈 Hide Checklist")
    hide_btn.set_tooltip_text("Hide the checklist while keeping this branch handoff window open")
    hide_btn.connect("clicked", lambda *_: self.hide())
    header.pack_end(hide_btn, False, False, 0)

    show_btn = Gtk.Button(label="👁 Checklist")
    show_btn.set_tooltip_text("Show the checklist again")
    show_btn.connect("clicked", lambda *_: (self.show(), self.present()))
    header.pack_end(show_btn, False, False, 0)

    root.pack_start(header, False, False, 0)
    root.pack_start(Gtk.Separator(), False, False, 0)

    branch_lbl = Gtk.Label(label="Branch name:")
    branch_lbl.set_halign(Gtk.Align.START)
    root.pack_start(branch_lbl, False, False, 0)

    branch_entry = Gtk.Entry()
    branch_entry.set_text(branch)
    branch_entry.set_editable(True)
    branch_entry.set_tooltip_text("Copyable branch name")
    root.pack_start(branch_entry, False, False, 0)

    stages = self._dwbh_branch_stages(branch)
    total_done = 0
    total_tasks = 0

    for stage in stages:
        done, total = checklists.progress_for_stage(stage)
        total_done += done
        total_tasks += total

    meta = Gtk.Label(label=f"{len(stages)} issue(s) • {total_done}/{total_tasks} complete • {_dwbh_progress_status(total_done, total_tasks)}")
    meta.set_halign(Gtk.Align.START)
    try:
        meta.get_style_context().add_class("stage-progress")
    except Exception:
        pass
    root.pack_start(meta, False, False, 0)

    desc_lbl = Gtk.Label(label="Full checklist description:")
    desc_lbl.set_halign(Gtk.Align.START)
    root.pack_start(desc_lbl, False, False, 0)

    desc_scroll = Gtk.ScrolledWindow()
    desc_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    desc_scroll.set_min_content_height(310)

    desc_view = Gtk.TextView()
    desc_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    desc_view.set_monospace(True)
    desc_buf = desc_view.get_buffer()
    desc_buf.set_text(self._dwbh_build_branch_description(branch))

    desc_scroll.add(desc_view)
    root.pack_start(desc_scroll, True, True, 0)

    status_lbl = Gtk.Label(label="Ready — copy branch name or checklist description.")
    status_lbl.set_halign(Gtk.Align.START)
    try:
        status_lbl.get_style_context().add_class("stage-progress")
    except Exception:
        pass

    btn_row = Gtk.Box(spacing=6)

    copy_branch_btn = Gtk.Button(label="📋 Branch")
    copy_branch_btn.set_tooltip_text("Copy branch name only")
    copy_branch_btn.connect("clicked", lambda *_: self._dwbh_copy_text(branch_entry.get_text().strip(), status_lbl, "Branch name copied"))
    btn_row.pack_start(copy_branch_btn, False, False, 0)

    copy_desc_btn = Gtk.Button(label="📋 Description")
    copy_desc_btn.set_tooltip_text("Copy full checklist description")
    copy_desc_btn.connect("clicked", lambda *_: self._dwbh_copy_text(_dwbh_buffer_text(desc_buf), status_lbl, "Checklist description copied"))
    btn_row.pack_start(copy_desc_btn, False, False, 0)

    copy_both_btn = Gtk.Button(label="📋 Both")
    copy_both_btn.set_tooltip_text("Copy branch name and full checklist description together")
    copy_both_btn.connect(
        "clicked",
        lambda *_: self._dwbh_copy_text(
            "Branch name:\n"
            + branch_entry.get_text().strip()
            + "\n\nChecklist description:\n"
            + _dwbh_buffer_text(desc_buf).strip()
            + "\n",
            status_lbl,
            "Branch name + description copied"
        )
    )
    btn_row.pack_start(copy_both_btn, False, False, 0)

    switch_btn = Gtk.Button(label="Create/Switch Git Branch")
    switch_btn.set_tooltip_text("Safely create or switch to this Git branch")
    switch_btn.connect("clicked", lambda *_: self._dwbh_create_or_switch_git_branch(branch_entry.get_text().strip(), status_lbl))
    btn_row.pack_start(switch_btn, False, False, 0)

    refresh_btn = Gtk.Button(label="↻ Refresh")
    refresh_btn.set_tooltip_text("Refresh description from current checklist data")
    refresh_btn.connect("clicked", lambda *_: (desc_buf.set_text(self._dwbh_build_branch_description(branch_entry.get_text().strip())), status_lbl.set_text("✅ Description refreshed")))
    btn_row.pack_start(refresh_btn, False, False, 0)

    close_btn = Gtk.Button(label="Close")
    close_btn.connect("clicked", lambda *_: win.destroy())
    btn_row.pack_end(close_btn, False, False, 0)

    root.pack_start(btn_row, False, False, 0)
    root.pack_start(status_lbl, False, False, 0)

    win.show_all()
    win.present()


def _dw_create_or_switch_issue_branch_handoff(self, _=None):
    branch = self._dwbh_selected_branch()

    if not branch:
        self._show_info("Click a checklist branch/folder row first, then press Branch.")
        return

    self._dwbh_open_window(branch)


def _dwbh_on_stage_list_button_press(self, widget, event):
    try:
        row = self.stage_list.get_row_at_y(int(event.y))

        if row is not None and getattr(row, "is_branch_header", False):
            branch = getattr(row, "branch_key", "") or "No branch"
            self._dw_selected_branch_key = branch
    except Exception:
        pass

    return ChecklistWindow._dwbh_base_stage_button_press(self, widget, event)


def _dwbh_on_stage_selected(self, listbox, row):
    try:
        if row is not None and getattr(row, "is_branch_header", False):
            self._dw_selected_branch_key = getattr(row, "branch_key", "") or "No branch"
            return

        if row is not None and hasattr(row, "stage_index"):
            stages = self.project_data.get("stages", [])
            if 0 <= row.stage_index < len(stages):
                branch = str(stages[row.stage_index].get("branch", "") or "").strip()
                if branch:
                    self._dw_selected_branch_key = branch
    except Exception:
        pass

    return ChecklistWindow._dwbh_base_stage_selected(self, listbox, row)


def _dwbh_make_branch_header_row(self, group):
    row = ChecklistWindow._dwbh_base_make_branch_header_row(self, group)

    try:
        row.branch_key = group.get("branch", "No branch")
        row.set_tooltip_text(
            "Click to open/close this branch.\n"
            "Then press Branch to open a copyable branch handoff window."
        )
    except Exception:
        pass

    return row


if not getattr(ChecklistWindow, "_dw_branch_handoff_window_patch_applied", False):
    ChecklistWindow._dwbh_stage_branch = _dwbh_stage_branch
    ChecklistWindow._dwbh_selected_branch = _dwbh_selected_branch
    ChecklistWindow._dwbh_branch_stages = _dwbh_branch_stages
    ChecklistWindow._dwbh_build_branch_description = _dwbh_build_branch_description
    ChecklistWindow._dwbh_copy_text = _dwbh_copy_text
    ChecklistWindow._dwbh_open_window = _dwbh_open_window
    ChecklistWindow._dwbh_create_or_switch_git_branch = _dwbh_create_or_switch_git_branch

    ChecklistWindow._dwbh_base_stage_button_press = ChecklistWindow._on_stage_list_button_press
    ChecklistWindow._dwbh_base_stage_selected = ChecklistWindow._on_stage_selected

    ChecklistWindow._on_stage_list_button_press = _dwbh_on_stage_list_button_press
    ChecklistWindow._on_stage_selected = _dwbh_on_stage_selected

    if hasattr(ChecklistWindow, "_dw_make_branch_header_row"):
        ChecklistWindow._dwbh_base_make_branch_header_row = ChecklistWindow._dw_make_branch_header_row
        ChecklistWindow._dw_make_branch_header_row = _dwbh_make_branch_header_row
    elif hasattr(ChecklistWindow, "_dw_make_branch_header_row_clean"):
        ChecklistWindow._dwbh_base_make_branch_header_row = ChecklistWindow._dw_make_branch_header_row_clean
        ChecklistWindow._dw_make_branch_header_row_clean = _dwbh_make_branch_header_row

    ChecklistWindow._dw_create_or_switch_issue_branch = _dw_create_or_switch_issue_branch_handoff
    ChecklistWindow._dw_branch_handoff_window_patch_applied = True



# ── DevWise clean branch issue handoff format patch ─────────────────────────
# Changes Branch Handoff from raw Git branch output into a GitHub-issue-ready
# handoff:
# - chore/placement-engineering-enhancements -> Placement Engineering Enhancements
# - Copyable issue title is the clean human title
# - Copyable body is a clean branch summary
# - Removes repeated Status/Progress noise per issue
# - Keeps the real Git branch available for Create/Switch Git Branch

def _dwbhs_human_branch_title(branch):
    import re

    raw = str(branch or "").strip()

    if not raw:
        return "Branch Summary"

    raw = raw.replace("refs/heads/", "").strip("/")

    parts = [p for p in raw.split("/") if p]

    if len(parts) > 1 and parts[0].lower() in {
        "feat", "fix", "chore", "docs", "doc", "test", "tests",
        "refactor", "style", "perf", "build", "ci", "release", "hotfix"
    }:
        raw = "/".join(parts[1:])

    raw = re.sub(r"[-_/]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    if not raw:
        return "Branch Summary"

    small_words = {"and", "or", "the", "a", "an", "to", "for", "of", "in", "on", "with"}
    acronyms = {"api", "cli", "ui", "ux", "gui", "ssh", "http", "https", "json", "csv", "sql", "ip"}

    words = []

    for index, word in enumerate(raw.split()):
        lower = word.lower()

        if lower in acronyms:
            words.append(lower.upper())
        elif index > 0 and lower in small_words:
            words.append(lower)
        else:
            words.append(lower[:1].upper() + lower[1:])

    return " ".join(words)


def _dwbhs_stage_note(stage):
    notes = str(stage.get("notes", "") or "").strip()
    branch_notes = str(stage.get("branch_notes", "") or "").strip()

    if notes:
        return notes

    return branch_notes


def _dwbhs_build_branch_description(self, branch):
    stages = self._dwbh_branch_stages(branch) if hasattr(self, "_dwbh_branch_stages") else []
    title = _dwbhs_human_branch_title(branch)

    lines = [
        f"# {title}",
        "",
    ]

    if not stages:
        lines.extend([
            "No checklist issues were found for this branch yet.",
            "",
            "## Testing checklist",
            "",
            "- [ ] Run the project from terminal",
            "- [ ] Confirm the branch checklist tasks match the implementation",
            "- [ ] Commit and push the related changes",
        ])
        return "\n".join(lines).rstrip() + "\n"

    for stage in stages:
        issue_title = (
            str(stage.get("issue", "") or "").strip()
            or str(stage.get("title", "") or "").strip()
            or "Untitled issue"
        )

        lines.extend([
            f"## Issue: {issue_title}",
            "",
        ])

        note = _dwbhs_stage_note(stage)

        if note:
            lines.extend([
                note,
                "",
            ])

        items = stage.get("items", []) or []

        if not items:
            lines.extend([
                "- [ ] Add implementation task",
                "",
            ])
            continue

        for item in items:
            task = str(item.get("text", "") or "").strip()

            if not task:
                continue

            tick = "x" if item.get("done") else " "
            lines.append(f"- [{tick}] {task}")

            desc = str(item.get("description", "") or "").strip()
            if desc:
                for desc_line in desc.splitlines():
                    desc_line = desc_line.strip()
                    if desc_line:
                        lines.append(f"  - {desc_line}")

        lines.append("")

    lines.extend([
        "## Testing checklist",
        "",
        "- [ ] Run the project from terminal",
        "- [ ] Confirm the branch checklist tasks match the implementation",
        "- [ ] Commit and push the related changes",
        "",
    ])

    return "\n".join(lines).rstrip() + "\n"


def _dwbhs_open_window(self, branch):
    if not branch:
        self._show_info("Click a checklist branch/folder row first, then press Branch.")
        return

    issue_title = _dwbhs_human_branch_title(branch)

    win = Gtk.Window(title="Branch Issue Handoff")
    win.set_default_size(760, 560)
    win.set_size_request(460, 340)
    win.set_resizable(True)
    win.set_keep_above(True)

    try:
        win.set_type_hint(Gdk.WindowTypeHint.UTILITY)
    except Exception:
        pass

    if not hasattr(self, "_dw_branch_handoff_windows"):
        self._dw_branch_handoff_windows = []

    self._dw_branch_handoff_windows.append(win)

    def _drop_ref(_win):
        try:
            self._dw_branch_handoff_windows.remove(_win)
        except Exception:
            pass

    win.connect("destroy", _drop_ref)

    root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
    root.set_border_width(12)
    win.add(root)

    header = Gtk.Box(spacing=8)

    heading = Gtk.Label()
    heading.set_markup("<b>Branch Issue Handoff</b>")
    heading.set_halign(Gtk.Align.START)
    header.pack_start(heading, True, True, 0)

    hide_btn = Gtk.Button(label="🙈 Hide Checklist")
    hide_btn.set_tooltip_text("Hide the checklist while keeping this handoff window open")
    hide_btn.connect("clicked", lambda *_: self.hide())
    header.pack_end(hide_btn, False, False, 0)

    show_btn = Gtk.Button(label="👁 Checklist")
    show_btn.set_tooltip_text("Show the checklist again")
    show_btn.connect("clicked", lambda *_: (self.show(), self.present()))
    header.pack_end(show_btn, False, False, 0)

    root.pack_start(header, False, False, 0)
    root.pack_start(Gtk.Separator(), False, False, 0)

    title_lbl = Gtk.Label(label="GitHub issue title:")
    title_lbl.set_halign(Gtk.Align.START)
    root.pack_start(title_lbl, False, False, 0)

    title_entry = Gtk.Entry()
    title_entry.set_text(issue_title)
    title_entry.set_editable(True)
    title_entry.set_tooltip_text("Copy this into the GitHub issue title.")
    root.pack_start(title_entry, False, False, 0)

    branch_lbl = Gtk.Label(label="Real Git branch:")
    branch_lbl.set_halign(Gtk.Align.START)
    root.pack_start(branch_lbl, False, False, 0)

    branch_entry = Gtk.Entry()
    branch_entry.set_text(branch)
    branch_entry.set_editable(True)
    branch_entry.set_tooltip_text("Copy this if you need the actual Git branch name.")
    root.pack_start(branch_entry, False, False, 0)

    stages = self._dwbh_branch_stages(branch) if hasattr(self, "_dwbh_branch_stages") else []
    total_done = 0
    total_tasks = 0

    for stage in stages:
        done, total = checklists.progress_for_stage(stage)
        total_done += done
        total_tasks += total

    meta = Gtk.Label(label=f"{len(stages)} issue(s) • {total_done}/{total_tasks} complete")
    meta.set_halign(Gtk.Align.START)
    try:
        meta.get_style_context().add_class("stage-progress")
    except Exception:
        pass
    root.pack_start(meta, False, False, 0)

    desc_lbl = Gtk.Label(label="GitHub issue body:")
    desc_lbl.set_halign(Gtk.Align.START)
    root.pack_start(desc_lbl, False, False, 0)

    desc_scroll = Gtk.ScrolledWindow()
    desc_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
    desc_scroll.set_min_content_height(300)

    desc_view = Gtk.TextView()
    desc_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
    desc_view.set_monospace(True)
    desc_buf = desc_view.get_buffer()
    desc_buf.set_text(self._dwbhs_build_branch_description(branch))

    desc_scroll.add(desc_view)
    root.pack_start(desc_scroll, True, True, 0)

    status_lbl = Gtk.Label(label="Ready — copy title/body into GitHub.")
    status_lbl.set_halign(Gtk.Align.START)
    try:
        status_lbl.get_style_context().add_class("stage-progress")
    except Exception:
        pass

    btn_row = Gtk.Box(spacing=6)

    copy_title_btn = Gtk.Button(label="📋 Title")
    copy_title_btn.set_tooltip_text("Copy clean GitHub issue title")
    copy_title_btn.connect(
        "clicked",
        lambda *_: self._dwbh_copy_text(
            title_entry.get_text().strip(),
            status_lbl,
            "Issue title copied"
        )
    )
    btn_row.pack_start(copy_title_btn, False, False, 0)

    copy_branch_btn = Gtk.Button(label="📋 Branch")
    copy_branch_btn.set_tooltip_text("Copy real Git branch name")
    copy_branch_btn.connect(
        "clicked",
        lambda *_: self._dwbh_copy_text(
            branch_entry.get_text().strip(),
            status_lbl,
            "Git branch copied"
        )
    )
    btn_row.pack_start(copy_branch_btn, False, False, 0)

    copy_body_btn = Gtk.Button(label="📋 Body")
    copy_body_btn.set_tooltip_text("Copy clean GitHub issue body")
    copy_body_btn.connect(
        "clicked",
        lambda *_: self._dwbh_copy_text(
            _dwbh_buffer_text(desc_buf) if "_dwbh_buffer_text" in globals() else "",
            status_lbl,
            "Issue body copied"
        )
    )
    btn_row.pack_start(copy_body_btn, False, False, 0)

    copy_both_btn = Gtk.Button(label="📋 Title + Body")
    copy_both_btn.set_tooltip_text("Copy title and body together")
    copy_both_btn.connect(
        "clicked",
        lambda *_: self._dwbh_copy_text(
            "GitHub issue title:\n"
            + title_entry.get_text().strip()
            + "\n\nGitHub issue body:\n"
            + (_dwbh_buffer_text(desc_buf).strip() if "_dwbh_buffer_text" in globals() else "")
            + "\n",
            status_lbl,
            "Issue title + body copied"
        )
    )
    btn_row.pack_start(copy_both_btn, False, False, 0)

    switch_btn = Gtk.Button(label="Create/Switch Git Branch")
    switch_btn.set_tooltip_text("Safely create or switch to the real Git branch")
    switch_btn.connect(
        "clicked",
        lambda *_: self._dwbh_create_or_switch_git_branch(branch_entry.get_text().strip(), status_lbl)
    )
    btn_row.pack_start(switch_btn, False, False, 0)

    refresh_btn = Gtk.Button(label="↻ Refresh")
    refresh_btn.set_tooltip_text("Refresh issue body from current checklist data")
    refresh_btn.connect(
        "clicked",
        lambda *_: (
            desc_buf.set_text(self._dwbhs_build_branch_description(branch_entry.get_text().strip())),
            title_entry.set_text(_dwbhs_human_branch_title(branch_entry.get_text().strip())),
            status_lbl.set_text("✅ Issue body refreshed")
        )
    )
    btn_row.pack_start(refresh_btn, False, False, 0)

    close_btn = Gtk.Button(label="Close")
    close_btn.connect("clicked", lambda *_: win.destroy())
    btn_row.pack_end(close_btn, False, False, 0)

    root.pack_start(btn_row, False, False, 0)
    root.pack_start(status_lbl, False, False, 0)

    win.show_all()
    win.present()


if not getattr(ChecklistWindow, "_dw_clean_branch_issue_handoff_format_applied", False):
    ChecklistWindow._dwbhs_build_branch_description = _dwbhs_build_branch_description
    ChecklistWindow._dwbh_build_branch_description = _dwbhs_build_branch_description
    ChecklistWindow._dwbh_open_window = _dwbhs_open_window
    ChecklistWindow._dw_clean_branch_issue_handoff_format_applied = True



# ── DevWise branch labels prompt/handoff patch ──────────────────────────────
# Adds branch-level labels to checklist prompting and branch handoff output.
# Intended GitHub labels examples:
# enhancement, bug, documentation, refactor, testing, frontend, backend,
# cli, web, security, priority-high, priority-medium, priority-low,
# dissertation, placement, good-first-issue, blocked

def _dwbl_prompt_subject(self):
    project_name = os.path.basename(os.path.abspath(self.project_path)) or "this project"

    if project_name.strip().lower() == "devwise":
        return "DevWise checklist"

    return f"{project_name} DevWise checklist"


def _dwbl_markdown_import_prompt(self):
    subject = self._dwbl_prompt_subject()

    return f"""Create or update a {subject}.

IMPORTANT OUTPUT RULE:
Return only one clean markdown code block. No explanation outside it.
Do not include citations, source labels, contentReference tags, oaicite tags, or tables.

Use this exact structure:

# Branch: feat/example-branch
Labels: enhancement, frontend, priority-medium
Notes: Optional branch/workstream context.

## Issue: Short issue title
Status: IN PROGRESS
Progress: 0 / 2 tasks complete

- First task name
Done: no
Descript: Useful detail for this task.

- Second task name
Done: no
Descript: Useful detail for this task.

Suggested label style:
- Use 2 to 6 labels per branch.
- Use labels that would also make sense on GitHub issues.
- Prefer lowercase kebab-case labels.
- Good examples: enhancement, bug, documentation, refactor, testing, frontend, backend, cli, web, security, priority-high, priority-medium, priority-low, dissertation, placement, good-first-issue, blocked.
- Use priority-high only for genuinely urgent or blocking work.
- Use blocked only when the work cannot continue without another task, decision, deadline, or dependency.
- Use dissertation for academic/report/evaluation branches.
- Use placement for employability, packaging, polish, engineering-quality or portfolio branches.

Rules:
- Use Branch for the Git branch/workstream.
- Use Labels directly under each Branch.
- Use Notes directly under each Branch for branch/workstream context.
- Use Issue for grouped work inside a branch.
- Use normal bullet points for tasks.
- Use Done: yes or Done: no under each task.
- Use Descript: directly under each task for task description.
- If updating an existing checklist, focus on active/incomplete work.
- Keep completed work only as completed context unless I explicitly ask for full completed tasks.
- Do not use checkbox syntax like [ ] or [x].
"""


def _dwbl_clean_labels(value):
    labels = []

    if isinstance(value, list):
        raw = ",".join(str(x) for x in value)
    else:
        raw = str(value or "")

    for part in raw.replace(";", ",").split(","):
        label = part.strip().strip("`").strip()

        if label and label not in labels:
            labels.append(label)

    return labels


def _dwbl_labels_for_branch(self, branch):
    labels = []

    for stage in self.project_data.get("stages", []):
        stage_branch = str(stage.get("branch", "") or "").strip() or "No branch"

        if stage_branch != branch:
            continue

        for label in _dwbl_clean_labels(stage.get("labels", [])):
            if label not in labels:
                labels.append(label)

    if labels:
        return labels

    # Sensible fallbacks when older checklists do not have Labels yet.
    lower = str(branch or "").lower()

    if "web" in lower:
        labels.extend(["enhancement", "web"])
    if "api" in lower:
        labels.extend(["enhancement", "backend"])
    if "cli" in lower:
        labels.extend(["enhancement", "cli"])
    if "security" in lower or "sentinel" in lower:
        labels.extend(["security"])
    if "docs" in lower or "dissertation" in lower:
        labels.extend(["documentation", "dissertation"])
    if "placement" in lower or "engineering" in lower:
        labels.extend(["enhancement", "placement"])
    if "fix" in lower or lower.startswith("bug"):
        labels.extend(["bug"])
    if "test" in lower or "eval" in lower:
        labels.extend(["testing"])

    if not labels:
        labels.extend(["enhancement", "priority-medium"])

    clean = []

    for label in labels:
        if label not in clean:
            clean.append(label)

    return clean


def _dwbl_stage_note(stage):
    notes = str(stage.get("notes", "") or "").strip()
    branch_notes = str(stage.get("branch_notes", "") or "").strip()

    if notes:
        return notes

    return branch_notes


def _dwbl_human_branch_title(branch):
    import re

    raw = str(branch or "").strip()

    if not raw:
        return "Branch Summary"

    raw = raw.replace("refs/heads/", "").strip("/")

    parts = [p for p in raw.split("/") if p]

    if len(parts) > 1 and parts[0].lower() in {
        "feat", "fix", "chore", "docs", "doc", "test", "tests",
        "refactor", "style", "perf", "build", "ci", "release", "hotfix"
    }:
        raw = "/".join(parts[1:])

    raw = re.sub(r"[-_/]+", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip()

    if not raw:
        return "Branch Summary"

    small_words = {"and", "or", "the", "a", "an", "to", "for", "of", "in", "on", "with"}
    acronyms = {"api", "cli", "ui", "ux", "gui", "ssh", "http", "https", "json", "csv", "sql", "ip"}

    words = []

    for index, word in enumerate(raw.split()):
        lower = word.lower()

        if lower in acronyms:
            words.append(lower.upper())
        elif index > 0 and lower in small_words:
            words.append(lower)
        else:
            words.append(lower[:1].upper() + lower[1:])

    return " ".join(words)


def _dwbl_build_branch_description(self, branch):
    stages = self._dwbh_branch_stages(branch) if hasattr(self, "_dwbh_branch_stages") else []
    title = _dwbl_human_branch_title(branch)
    labels = self._dwbl_labels_for_branch(branch)

    lines = [
        f"# {title}",
        "",
        "Labels: " + ", ".join(labels),
        "",
    ]

    if not stages:
        lines.extend([
            "No checklist issues were found for this branch yet.",
            "",
            "## Testing checklist",
            "",
            "- [ ] Run the project from terminal",
            "- [ ] Confirm the branch checklist tasks match the implementation",
            "- [ ] Commit and push the related changes",
        ])
        return "\n".join(lines).rstrip() + "\n"

    for stage in stages:
        issue_title = (
            str(stage.get("issue", "") or "").strip()
            or str(stage.get("title", "") or "").strip()
            or "Untitled issue"
        )

        lines.extend([
            f"## Issue: {issue_title}",
            "",
        ])

        note = _dwbl_stage_note(stage)

        if note:
            lines.extend([
                note,
                "",
            ])

        items = stage.get("items", []) or []

        if not items:
            lines.extend([
                "- [ ] Add implementation task",
                "",
            ])
            continue

        for item in items:
            task = str(item.get("text", "") or "").strip()

            if not task:
                continue

            tick = "x" if item.get("done") else " "
            lines.append(f"- [{tick}] {task}")

            desc = str(item.get("description", "") or "").strip()
            if desc:
                for desc_line in desc.splitlines():
                    desc_line = desc_line.strip()
                    if desc_line:
                        lines.append(f"  - {desc_line}")

        lines.append("")

    lines.extend([
        "## Testing checklist",
        "",
        "- [ ] Run the project from terminal",
        "- [ ] Confirm the branch checklist tasks match the implementation",
        "- [ ] Commit and push the related changes",
        "",
    ])

    return "\n".join(lines).rstrip() + "\n"


if not getattr(ChecklistWindow, "_dw_branch_labels_prompt_handoff_patch_applied", False):
    ChecklistWindow._dwbl_prompt_subject = _dwbl_prompt_subject
    ChecklistWindow._markdown_import_prompt = _dwbl_markdown_import_prompt
    ChecklistWindow._dwbl_labels_for_branch = _dwbl_labels_for_branch
    ChecklistWindow._dwbl_build_branch_description = _dwbl_build_branch_description

    # Make Branch Handoff use the new body with Labels.
    ChecklistWindow._dwbhs_build_branch_description = _dwbl_build_branch_description
    ChecklistWindow._dwbh_build_branch_description = _dwbl_build_branch_description

    ChecklistWindow._dw_branch_labels_prompt_handoff_patch_applied = True

