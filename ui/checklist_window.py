"""Project Checklist / Roadmap window — standalone Gtk.Window per project."""
import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, Gdk

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
            "Paste a markdown roadmap below.\n"
            "Headings (<tt>#</tt>, <tt>##</tt>, ...) become <b>stages</b>.\n"
            "Use <tt>Notes:</tt> under a stage for stage-level notes.\n"
            "Use bullet lines (<tt>- Task</tt>) or numbered lines for <b>checklist items</b>.\n"
            "Use <tt>Descript:</tt> directly under a task for its <b>Task Description</b>.\n"
            "Do not use checkbox syntax like <tt>[ ]</tt> or <tt>[x]</tt>."
        )
        hint.set_halign(Gtk.Align.START)
        hint.set_line_wrap(True)
        box.pack_start(hint, False, False, 0)


        prompt_row = Gtk.Box(spacing=6)

        copy_prompt_btn = Gtk.Button(label="📋 Copy Markdown Checklist Format")
        copy_prompt_btn.set_tooltip_text("Copy the markdown checklist format to clipboard")
        copy_prompt_btn.connect("clicked", self._copy_markdown_import_prompt)
        prompt_row.pack_start(copy_prompt_btn, False, False, 0)

        example_lbl = Gtk.Label(label="Markdown format: # Stage → Notes: → - Task → Descript:")
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
