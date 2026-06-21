"""Table Lab — simple CLI table spacing designer/debugger."""
import ast
import re
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GLib

from core import table_lab


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

EXAMPLE_CALLER = '''print_section_header(
    "Suspicious IPs (Failed Attempts)",
    Fore.YELLOW
)

attempt_colour = get_count_colour(len(results))

print_total_count(
    "Suspicious IPs Detected",
    len(results),
    attempt_colour
)

columns = [
    ("IP Address", 15),
    ("Attempts", 12, "^"),
    ("Status", 20, "^"),
    ("Severity", 15)
]

print_table_header(columns)

for result in results:

    severity_colour = get_severity_colour(
        result.severity
    )

    attempt_colour = get_attempt_colour(result.attempts)

    print(
        "   "
        + attempt_colour
        + format_column(result.ip, 15)
        + format_column(result.attempts, 12, "^")
        + format_column(result.risk_status, 20, "^")
        + severity_colour
        + format_column(result.severity, 15)
    )
'''

EXAMPLE_OUTPUT = '''=== Suspicious IPs (Failed Attempts) ===

   Suspicious IPs Detected: 7

   IP Address       Attempts         Status       Severity       
   -----------------------------------------------------------------
   203.0.113.11        5          Investigate     LOW            
   203.0.113.20        3            Low risk      LOW            
   203.0.113.1         1            Low risk      LOW            
   203.0.113.2         1            Low risk      LOW            
   203.0.113.3         1            Low risk      LOW            
   203.0.113.4         1            Low risk      LOW            
   203.0.113.5         1            Low risk      LOW            
'''


def strip_ansi(text):
    return ANSI_RE.sub("", text or "")


def format_cell(value, width, align="<"):
    try:
        width = int(width)
    except Exception:
        width = 10

    align = align if align in ("<", "^", ">") else "<"
    return f"{str(value):{align}{width}}"


class TableLabWindow(Gtk.Window):
    def __init__(self, parent=None):
        super().__init__(title="🧪 Table Lab")
        self.parent_window = parent

        # Standalone window — do not use set_transient_for(parent).
        # This allows Table Lab to stay open if the main window is hidden.
        self.set_default_size(860, 560)
        self.set_size_request(660, 420)
        self.set_resizable(True)

        self.current_session_id = None
        self.selected_function_id = None
        self.parsed_rows = []
        self.prefix_lines = []
        self.source_column_defs = []

        self._loading = False
        self._programmatic = False
        self._syncing_column_controls = False
        self._dirty = False
        self._autosave_timeout = None

        self._apply_css()
        self._build()
        self._refresh_function_list()
        self._refresh_session_combo()
        self._load_first_function()
        self._update_column_controls()
        self._update_dirty_label()

        self.connect("delete-event", self._on_close)
        self.show_all()
        self.set_position(Gtk.WindowPosition.CENTER)
        GLib.idle_add(self.present)

    # ── Window behaviour ────────────────────────────────────────────────────

    def present_bottom_left(self):
        self.set_position(Gtk.WindowPosition.CENTER)
        self.present()
        return False

    def _on_toggle_main_window(self, btn):
        parent = getattr(self, "parent_window", None)

        if parent is None:
            btn.set_active(False)
            return

        if btn.get_active():
            parent.hide()
            btn.set_label("👁 Show Main")
            self.present()
        else:
            parent.show()
            parent.present()
            btn.set_label("🙈 Hide Main")

    def _restore_main_window_if_hidden(self):
        parent = getattr(self, "parent_window", None)

        if parent is not None and not parent.get_visible():
            parent.show()
            parent.present()

    def _on_close(self, _window, _event):
        if self._dirty and not self.autosave_switch.get_active():
            response = self._save_discard_cancel(
                "You have unsaved Table Lab changes.\nSave this session before closing?"
            )

            if response == "cancel":
                return True

            if response == "save":
                self._save_session()

        elif self._dirty and self.autosave_switch.get_active():
            self._save_session(silent=True)

        self._restore_main_window_if_hidden()
        return False

    # ── Styling / small helpers ─────────────────────────────────────────────

    def _apply_css(self):
        css = b"""
        .lab-toolbar {
            background: alpha(white, 0.04);
            border-bottom: 1px solid alpha(white, 0.08);
            padding: 6px;
        }
        .lab-section-title {
            font-weight: bold;
            font-size: 12px;
        }
        .lab-muted {
            opacity: 0.62;
            font-size: 10px;
        }
        .lab-code {
            font-family: monospace;
            font-size: 11px;
        }
        .lab-step {
            font-weight: bold;
            font-size: 13px;
        }
        .lab-unsaved {
            color: #f39c12;
            font-size: 11px;
        }
        .lab-saved {
            color: #2ecc71;
            font-size: 11px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _label(self, text, muted=False, step=False):
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)

        if step:
            lbl.get_style_context().add_class("lab-step")
        elif muted:
            lbl.get_style_context().add_class("lab-muted")
        else:
            lbl.get_style_context().add_class("lab-section-title")

        return lbl

    def _text_view(self, editable=True, wrap=False):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        buf = Gtk.TextBuffer()
        view = Gtk.TextView(buffer=buf)
        view.set_editable(editable)
        view.set_monospace(True)
        view.get_style_context().add_class("lab-code")
        view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR if wrap else Gtk.WrapMode.NONE)

        scroll.add(view)
        return scroll, view, buf

    def _get_text(self, buf):
        start, end = buf.get_bounds()
        return buf.get_text(start, end, False)

    def _set_text(self, buf, text, mark=False):
        self._programmatic = True
        buf.set_text(text or "")
        self._programmatic = False

        if mark:
            self._mark_dirty()

    def _copy_text(self, text, label="Copied."):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text or "", -1)
        self.status_lbl.set_text("✅ " + label)

    def _show_info(self, message, title="Table Lab"):
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=title,
        )
        dlg.format_secondary_text(message)
        dlg.run()
        dlg.destroy()

    def _save_discard_cancel(self, message):
        dlg = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.NONE,
            text="Unsaved Table Lab session",
        )
        dlg.format_secondary_text(message)
        dlg.add_button("Discard", Gtk.ResponseType.REJECT)
        dlg.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        dlg.add_button("Save", Gtk.ResponseType.ACCEPT)
        dlg.set_default_response(Gtk.ResponseType.ACCEPT)

        response = dlg.run()
        dlg.destroy()

        if response == Gtk.ResponseType.ACCEPT:
            return "save"
        if response == Gtk.ResponseType.REJECT:
            return "discard"
        return "cancel"

    # ── Layout ──────────────────────────────────────────────────────────────

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)

        toolbar_scroll = Gtk.ScrolledWindow()
        toolbar_scroll.set_policy(Gtk.PolicyType.EXTERNAL, Gtk.PolicyType.NEVER)
        toolbar_scroll.set_propagate_natural_height(True)

        toolbar = Gtk.Box(spacing=6)
        toolbar.get_style_context().add_class("lab-toolbar")
        toolbar_scroll.add(toolbar)

        toolbar.pack_start(self._label("Session:", muted=True), False, False, 0)

        self.session_name_entry = Gtk.Entry()
        self.session_name_entry.set_width_chars(22)
        self.session_name_entry.set_placeholder_text("e.g. Suspicious IPs table")
        self.session_name_entry.connect("changed", self._on_text_changed)
        toolbar.pack_start(self.session_name_entry, False, False, 0)

        save_btn = Gtk.Button(label="💾 Save")
        save_btn.set_tooltip_text("Save this Table Lab session")
        save_btn.connect("clicked", lambda _: self._save_session())
        toolbar.pack_start(save_btn, False, False, 0)

        new_btn = Gtk.Button(label="New")
        new_btn.connect("clicked", self._new_session)
        toolbar.pack_start(new_btn, False, False, 0)

        toolbar.pack_start(self._label("Recent:", muted=True), False, False, 0)

        self.recent_combo = Gtk.ComboBoxText()
        self.recent_combo.set_tooltip_text("Load a recent Table Lab session")
        self.recent_combo.connect("changed", self._on_recent_session_changed)
        toolbar.pack_start(self.recent_combo, False, False, 0)

        self.autosave_switch = Gtk.Switch()
        self.autosave_switch.set_active(True)
        self.autosave_switch.connect("notify::active", self._on_autosave_toggled)

        autosave_box = Gtk.Box(spacing=4)
        autosave_box.pack_start(self._label("Autosave", muted=True), False, False, 0)
        autosave_box.pack_start(self.autosave_switch, False, False, 0)
        toolbar.pack_start(autosave_box, False, False, 8)

        parse_btn = Gtk.Button(label="1 Parse")
        parse_btn.set_tooltip_text("Parse columns from the Table Caller and rows from Original Output")
        parse_btn.connect("clicked", self._parse_everything)
        toolbar.pack_start(parse_btn, False, False, 0)

        preview_btn = Gtk.Button(label="2 Preview")
        preview_btn.set_tooltip_text("Build the updated preview")
        preview_btn.connect("clicked", self._build_preview)
        toolbar.pack_start(preview_btn, False, False, 0)

        code_btn = Gtk.Button(label="3 Generate Code")
        code_btn.set_tooltip_text("Generate updated replacement code")
        code_btn.connect("clicked", self._generate_replacement_code)
        toolbar.pack_start(code_btn, False, False, 0)

        copy_btn = Gtk.Button(label="📋 Copy Code")
        copy_btn.set_tooltip_text("Copy Generated Replacement Code")
        copy_btn.connect("clicked", lambda _: self._copy_text(
            self._get_text(self.generated_buf),
            "Generated Replacement Code copied."
        ))
        toolbar.pack_start(copy_btn, False, False, 0)

        help_btn = Gtk.Button(label="Help")
        help_btn.connect("clicked", self._show_help)
        toolbar.pack_start(help_btn, False, False, 0)

        self.main_win_btn = Gtk.ToggleButton(label="🙈 Hide Main")
        self.main_win_btn.connect("toggled", self._on_toggle_main_window)
        toolbar.pack_start(self.main_win_btn, False, False, 0)

        self.status_lbl = Gtk.Label(label="Ready")
        self.status_lbl.set_halign(Gtk.Align.START)
        toolbar.pack_start(self.status_lbl, True, True, 0)

        self.dirty_lbl = Gtk.Label(label="")
        self.dirty_lbl.set_halign(Gtk.Align.END)
        toolbar.pack_end(self.dirty_lbl, False, False, 0)

        root.pack_start(toolbar_scroll, False, False, 0)

        self.notebook = Gtk.Notebook()
        root.pack_start(self.notebook, True, True, 0)

        self.notebook.append_page(self._build_input_tab(), Gtk.Label(label="1 Input"))
        self.notebook.append_page(self._build_tune_tab(), Gtk.Label(label="2 Tune"))
        self.notebook.append_page(self._build_code_tab(), Gtk.Label(label="3 Code"))
        self.notebook.append_page(self._build_helpers_tab(), Gtk.Label(label="Helpers"))

    def _build_input_tab(self):
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(420)

        caller_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        caller_box.set_border_width(8)

        caller_header = Gtk.Box(spacing=6)
        caller_header.pack_start(self._label("Table Caller", step=True), True, True, 0)

        load_caller_btn = Gtk.Button(label="Load Example")
        load_caller_btn.connect("clicked", self._load_example_caller)
        caller_header.pack_end(load_caller_btn, False, False, 0)

        copy_caller_btn = Gtk.Button(label="Copy")
        copy_caller_btn.connect("clicked", lambda _: self._copy_text(
            self._get_text(self.caller_buf),
            "caller copied."
        ))
        caller_header.pack_end(copy_caller_btn, False, False, 0)

        caller_box.pack_start(caller_header, False, False, 0)
        caller_box.pack_start(
            self._label("Paste the Python block that contains columns = [...] and the print loop.", muted=True),
            False, False, 0
        )

        caller_scroll, self.caller_view, self.caller_buf = self._text_view(editable=True)
        self.caller_buf.connect("changed", self._on_text_changed)
        caller_box.pack_start(caller_scroll, True, True, 0)

        output_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        output_box.set_border_width(8)

        output_header = Gtk.Box(spacing=6)
        output_header.pack_start(self._label("Original Output", step=True), True, True, 0)

        load_output_btn = Gtk.Button(label="Load Example")
        load_output_btn.connect("clicked", self._load_example_original)
        output_header.pack_end(load_output_btn, False, False, 0)

        parse_rows_btn = Gtk.Button(label="Parse Rows")
        parse_rows_btn.connect("clicked", self._parse_original_rows)
        output_header.pack_end(parse_rows_btn, False, False, 0)

        infer_btn = Gtk.Button(label="Infer Table")
        infer_btn.set_tooltip_text("Infer columns and rows directly from Original Output without needing Table Caller")
        infer_btn.connect("clicked", self._infer_from_original_output)
        output_header.pack_end(infer_btn, False, False, 0)

        output_box.pack_start(output_header, False, False, 0)
        output_box.pack_start(
            self._label("Paste the terminal output for this table. This lets the preview use real rows.", muted=True),
            False, False, 0
        )

        original_scroll, self.original_view, self.original_buf = self._text_view(editable=True)
        self.original_buf.connect("changed", self._on_original_changed)
        output_box.pack_start(original_scroll, True, True, 0)

        paned.pack1(caller_box, resize=True, shrink=False)
        paned.pack2(output_box, resize=True, shrink=False)
        return paned

    def _build_tune_tab(self):
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(385)

        editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        editor_box.set_border_width(8)

        editor_box.pack_start(self._label("Column Editor", step=True), False, False, 0)
        editor_box.pack_start(
            self._label("Drag rows to reorder columns, or use Move Up / Move Down.", muted=True),
            False, False, 0
        )

        control_grid = Gtk.Grid(column_spacing=6, row_spacing=6)
        control_grid.set_margin_bottom(4)

        add_btn = Gtk.Button(label="+ Blank Column")
        add_btn.connect("clicked", self._add_column)
        control_grid.attach(add_btn, 0, 0, 1, 1)

        remove_btn = Gtk.Button(label="Remove")
        remove_btn.connect("clicked", self._remove_selected_column)
        control_grid.attach(remove_btn, 1, 0, 1, 1)

        up_btn = Gtk.Button(label="↑ Move")
        up_btn.connect("clicked", lambda _: self._move_selected_column(-1))
        control_grid.attach(up_btn, 2, 0, 1, 1)

        down_btn = Gtk.Button(label="↓ Move")
        down_btn.connect("clicked", lambda _: self._move_selected_column(1))
        control_grid.attach(down_btn, 3, 0, 1, 1)

        control_grid.attach(Gtk.Label(label="Width"), 0, 1, 1, 1)

        self.width_spin = Gtk.SpinButton()
        self.width_spin.set_range(1, 80)
        self.width_spin.set_increments(1, 5)
        self.width_spin.set_value(12)
        self.width_spin.set_tooltip_text("Selected column width. Use arrows or scroll to adjust live.")
        self.width_spin.connect("value-changed", self._on_width_spin_changed)
        control_grid.attach(self.width_spin, 1, 1, 1, 1)

        control_grid.attach(Gtk.Label(label="Align"), 2, 1, 1, 1)

        prev_align_btn = Gtk.Button(label="‹")
        prev_align_btn.set_tooltip_text("Previous alignment")
        prev_align_btn.connect("clicked", lambda _: self._cycle_align(-1))
        control_grid.attach(prev_align_btn, 3, 1, 1, 1)

        self.align_combo = Gtk.ComboBoxText()
        self.align_combo.append("<", "Left")
        self.align_combo.append("^", "Centre")
        self.align_combo.append(">", "Right")
        self.align_combo.set_active_id("<")
        self.align_combo.set_tooltip_text("Selected column alignment")
        self.align_combo.connect("changed", self._on_align_changed)
        control_grid.attach(self.align_combo, 4, 1, 1, 1)

        next_align_btn = Gtk.Button(label="›")
        next_align_btn.set_tooltip_text("Next alignment")
        next_align_btn.connect("clicked", lambda _: self._cycle_align(1))
        control_grid.attach(next_align_btn, 5, 1, 1, 1)

        editor_box.pack_start(control_grid, False, False, 0)

        preview_settings = Gtk.Box(spacing=8)

        preview_settings.pack_start(Gtk.Label(label="Indent"), False, False, 0)
        self.indent_spin = Gtk.SpinButton()
        self.indent_spin.set_range(0, 12)
        self.indent_spin.set_increments(1, 1)
        self.indent_spin.set_value(3)
        self.indent_spin.set_tooltip_text("Spaces before each table row.")
        self.indent_spin.connect("value-changed", lambda _: self._preview_setting_changed())
        preview_settings.pack_start(self.indent_spin, False, False, 0)

        gap_lbl = Gtk.Label(label="Extra gap")
        gap_lbl.set_tooltip_text(
            "Extra gap means extra spaces inserted BETWEEN columns in the preview. "
            "Use 0 if your format_column widths already create enough spacing."
        )
        preview_settings.pack_start(gap_lbl, False, False, 0)

        self.gap_spin = Gtk.SpinButton()
        self.gap_spin.set_range(0, 8)
        self.gap_spin.set_increments(1, 1)
        self.gap_spin.set_value(0)
        self.gap_spin.set_tooltip_text(
            "Extra spaces between columns in the preview. Usually keep this at 0."
        )
        self.gap_spin.connect("value-changed", lambda _: self._preview_setting_changed())
        preview_settings.pack_start(self.gap_spin, False, False, 0)

        preview_settings.pack_start(Gtk.Label(label="Separator"), False, False, 0)
        self.separator_entry = Gtk.Entry()
        self.separator_entry.set_width_chars(3)
        self.separator_entry.set_text("-")
        self.separator_entry.set_tooltip_text("Character used for the table separator line.")
        self.separator_entry.connect("changed", lambda _: self._preview_setting_changed())
        preview_settings.pack_start(self.separator_entry, False, False, 0)

        editor_box.pack_start(preview_settings, False, False, 0)

        self.column_store = Gtk.ListStore(str, int, str)
        self.column_store.connect("row-changed", self._on_columns_changed)
        self.column_store.connect("row-inserted", self._on_columns_changed)
        self.column_store.connect("row-deleted", self._on_columns_changed)

        self.column_tree = Gtk.TreeView(model=self.column_store)
        self.column_tree.set_headers_visible(True)
        self.column_tree.set_reorderable(True)
        self.column_tree.set_tooltip_text("Drag rows up/down to reorder table columns.")

        selection = self.column_tree.get_selection()
        selection.connect("changed", self._on_column_selection_changed)

        self._add_tree_column("Title", 0)
        self._add_tree_column("Width", 1)
        self._add_tree_column("Align", 2)

        column_scroll = Gtk.ScrolledWindow()
        column_scroll.add(self.column_tree)
        editor_box.pack_start(column_scroll, True, True, 0)

        preset_row = Gtk.Box(spacing=6)

        compact_btn = Gtk.Button(label="Compact")
        compact_btn.connect("clicked", lambda _: self._apply_preset("compact"))
        preset_row.pack_start(compact_btn, False, False, 0)

        readable_btn = Gtk.Button(label="Readable")
        readable_btn.connect("clicked", lambda _: self._apply_preset("readable"))
        preset_row.pack_start(readable_btn, False, False, 0)

        wide_btn = Gtk.Button(label="Wide")
        wide_btn.connect("clicked", lambda _: self._apply_preset("wide"))
        preset_row.pack_start(wide_btn, False, False, 0)

        editor_box.pack_start(preset_row, False, False, 0)

        preview_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        preview_box.set_border_width(8)

        preview_header = Gtk.Box(spacing=6)
        preview_header.pack_start(self._label("Updated Preview", step=True), True, True, 0)

        copy_preview_btn = Gtk.Button(label="Copy Preview")
        copy_preview_btn.connect("clicked", lambda _: self._copy_text(
            self._get_text(self.preview_buf),
            "preview copied."
        ))
        preview_header.pack_end(copy_preview_btn, False, False, 0)

        preview_box.pack_start(preview_header, False, False, 0)
        preview_box.pack_start(
            self._label("Adjust widths/alignment and this preview updates live.", muted=True),
            False, False, 0
        )

        preview_scroll, self.preview_view, self.preview_buf = self._text_view(editable=False)
        preview_box.pack_start(preview_scroll, True, True, 0)

        paned.pack1(editor_box, resize=False, shrink=False)
        paned.pack2(preview_box, resize=True, shrink=False)
        return paned

    def _build_code_tab(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)

        header = Gtk.Box(spacing=6)
        header.pack_start(self._label("Generated Replacement Code", step=True), True, True, 0)

        generate_btn = Gtk.Button(label="Generate")
        generate_btn.connect("clicked", self._generate_replacement_code)
        header.pack_end(generate_btn, False, False, 0)

        copy_btn = Gtk.Button(label="📋 Copy Generated Code")
        copy_btn.connect("clicked", lambda _: self._copy_text(
            self._get_text(self.generated_buf),
            "Generated Replacement Code copied."
        ))
        header.pack_end(copy_btn, False, False, 0)

        box.pack_start(header, False, False, 0)
        box.pack_start(
            self._label("Paste this back into SentinelIR to replace the original table caller block.", muted=True),
            False, False, 0
        )

        generated_scroll, self.generated_view, self.generated_buf = self._text_view(editable=True, wrap=False)
        self.generated_buf.connect("changed", self._on_text_changed)
        box.pack_start(generated_scroll, True, True, 0)
        return box

    def _build_helpers_tab(self):
        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(230)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        left.set_border_width(8)

        left.pack_start(self._label("Table Helpers", step=True), False, False, 0)

        self.function_list = Gtk.ListBox()
        self.function_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.function_list.connect("row-selected", self._on_function_selected)

        function_list_scroll = Gtk.ScrolledWindow()
        function_list_scroll.add(self.function_list)
        left.pack_start(function_list_scroll, True, True, 0)

        helper_btn_row = Gtk.Box(spacing=6)

        new_btn = Gtk.Button(label="New")
        new_btn.connect("clicked", self._new_function)
        helper_btn_row.pack_start(new_btn, True, True, 0)

        delete_btn = Gtk.Button(label="Delete")
        delete_btn.connect("clicked", self._delete_function)
        helper_btn_row.pack_start(delete_btn, True, True, 0)

        left.pack_start(helper_btn_row, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        right.set_border_width(8)

        right.pack_start(self._label("Helper Snippet", step=True), False, False, 0)

        self.function_name_entry = Gtk.Entry()
        self.function_name_entry.set_placeholder_text("Table Helpers")
        right.pack_start(self.function_name_entry, False, False, 0)

        function_scroll, self.function_view, self.function_buf = self._text_view(editable=True)
        right.pack_start(function_scroll, True, True, 0)

        function_btn_row = Gtk.Box(spacing=6)

        save_btn = Gtk.Button(label="Save Helpers")
        save_btn.connect("clicked", self._save_function)
        function_btn_row.pack_start(save_btn, False, False, 0)

        copy_btn = Gtk.Button(label="Copy Helpers")
        copy_btn.connect("clicked", lambda _: self._copy_text(
            self._get_text(self.function_buf),
            "helpers copied."
        ))
        function_btn_row.pack_start(copy_btn, False, False, 0)

        load_btn = Gtk.Button(label="Load Default")
        load_btn.connect("clicked", self._load_default_helpers)
        function_btn_row.pack_end(load_btn, False, False, 0)

        right.pack_start(function_btn_row, False, False, 0)

        paned.pack1(left, resize=False, shrink=False)
        paned.pack2(right, resize=True, shrink=False)
        return paned

    def _add_tree_column(self, title, model_index):
        renderer = Gtk.CellRendererText()
        renderer.set_property("editable", True)
        renderer.connect("edited", self._on_tree_cell_edited, model_index)

        column = Gtk.TreeViewColumn(title, renderer, text=model_index)
        column.set_resizable(True)
        column.set_expand(True)
        self.column_tree.append_column(column)

    # ── Dirty/session save ──────────────────────────────────────────────────

    def _on_text_changed(self, *_):
        if self._loading or self._programmatic:
            return

        self._mark_dirty()

    def _on_original_changed(self, *_):
        if self._loading or self._programmatic:
            return

        self.parsed_rows = []
        self.prefix_lines = []
        self._mark_dirty()

    def _mark_dirty(self):
        if self._loading:
            return

        self._dirty = True
        self._update_dirty_label()

        if hasattr(self, "autosave_switch") and self.autosave_switch.get_active():
            self._schedule_autosave()

    def _update_dirty_label(self):
        if not hasattr(self, "dirty_lbl"):
            return

        ctx = self.dirty_lbl.get_style_context()
        ctx.remove_class("lab-unsaved")
        ctx.remove_class("lab-saved")

        if self._dirty:
            self.dirty_lbl.set_text("Unsaved")
            ctx.add_class("lab-unsaved")
        else:
            self.dirty_lbl.set_text("Saved")
            ctx.add_class("lab-saved")

    def _on_autosave_toggled(self, *_):
        if self.autosave_switch.get_active() and self._dirty:
            self._schedule_autosave()

    def _schedule_autosave(self):
        if self._autosave_timeout:
            GLib.source_remove(self._autosave_timeout)

        self._autosave_timeout = GLib.timeout_add(900, self._do_autosave)

    def _do_autosave(self):
        self._autosave_timeout = None

        if self._dirty and self.autosave_switch.get_active():
            self._save_session(silent=True)

        return False

    def _collect_payload(self):
        return {
            "caller": self._get_text(self.caller_buf),
            "original": self._get_text(self.original_buf),
            "generated": self._get_text(self.generated_buf),
            "columns": [
                [str(row[0]), int(row[1]), str(row[2])]
                for row in self.column_store
            ],
            "indent": int(self.indent_spin.get_value()),
            "gap": int(self.gap_spin.get_value()),
            "separator": self.separator_entry.get_text() or "-",
            "parsed_rows": self.parsed_rows,
            "prefix_lines": self.prefix_lines,
            "source_column_defs": self.source_column_defs,
        }

    def _apply_payload(self, payload):
        payload = payload or {}
        self._loading = True

        self._set_text(self.caller_buf, payload.get("caller", ""))
        self._set_text(self.original_buf, payload.get("original", ""))
        self._set_text(self.generated_buf, payload.get("generated", ""))

        self.column_store.clear()
        for col in payload.get("columns", []):
            try:
                title, width, align = col
                self.column_store.append([str(title), int(width), str(align)])
            except Exception:
                pass

        self.indent_spin.set_value(int(payload.get("indent", 3)))
        self.gap_spin.set_value(int(payload.get("gap", 0)))
        self.separator_entry.set_text(payload.get("separator", "-"))

        self.parsed_rows = payload.get("parsed_rows", [])
        self.prefix_lines = payload.get("prefix_lines", [])
        self.source_column_defs = payload.get("source_column_defs", [])

        self._loading = False
        self._build_preview()
        self._dirty = False
        self._update_dirty_label()
        self._update_column_controls()

    def _save_session(self, _=None, silent=False):
        name = self.session_name_entry.get_text().strip() or "Untitled Table Session"

        session = table_lab.save_session(
            self.current_session_id,
            name,
            self._collect_payload()
        )

        self.current_session_id = session.get("id")
        self._dirty = False
        self._update_dirty_label()
        self._refresh_session_combo(select_id=self.current_session_id)

        if not silent:
            self.status_lbl.set_text("✅ Session saved.")

    def _new_session(self, _=None):
        if self._dirty and not self.autosave_switch.get_active():
            response = self._save_discard_cancel("Save current session before starting a new one?")

            if response == "cancel":
                return

            if response == "save":
                self._save_session()

        self.current_session_id = None
        self.session_name_entry.set_text("")
        self._apply_payload({})
        self.status_lbl.set_text("New Table Lab session.")
        self.notebook.set_current_page(0)

    def _refresh_session_combo(self, select_id=None):
        if not hasattr(self, "recent_combo"):
            return

        self._loading = True
        self.recent_combo.remove_all()
        self.recent_combo.append("_none", "Recent sessions")

        active_index = 0

        for index, session in enumerate(table_lab.list_sessions(), start=1):
            sid = session.get("id")
            name = session.get("name", "Untitled Table Session")
            self.recent_combo.append(sid, name)

            if sid == select_id:
                active_index = index

        self.recent_combo.set_active(active_index)
        self._loading = False

    def _on_recent_session_changed(self, combo):
        if self._loading:
            return

        session_id = combo.get_active_id()

        if not session_id or session_id == "_none":
            return

        if self._dirty and not self.autosave_switch.get_active():
            response = self._save_discard_cancel("Save current session before loading another one?")

            if response == "cancel":
                self._refresh_session_combo(select_id=self.current_session_id)
                return

            if response == "save":
                self._save_session()

        session = table_lab.get_session(session_id)

        if not session:
            return

        self.current_session_id = session_id
        self.session_name_entry.set_text(session.get("name", "Untitled Table Session"))
        self._apply_payload(session.get("payload", {}))
        self.status_lbl.set_text(f"Loaded: {session.get('name', 'session')}")

    # ── Helper snippets ─────────────────────────────────────────────────────

    def _refresh_function_list(self):
        for child in self.function_list.get_children():
            self.function_list.remove(child)

        for item in table_lab.list_functions():
            row = Gtk.ListBoxRow()
            row.function_id = item.get("id")
            row.function_data = item

            label = Gtk.Label(label=item.get("name", "Table Helpers"))
            label.set_halign(Gtk.Align.START)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_margin_top(5)
            label.set_margin_bottom(5)
            label.set_margin_start(5)
            label.set_margin_end(5)

            row.add(label)
            self.function_list.add(row)

        self.function_list.show_all()

    def _load_first_function(self):
        row = self.function_list.get_row_at_index(0)

        if row is not None:
            self.function_list.select_row(row)

    def _on_function_selected(self, _listbox, row):
        if row is None or not hasattr(row, "function_data"):
            return

        data = row.function_data
        self.selected_function_id = data.get("id")
        self.function_name_entry.set_text(data.get("name", "Table Helpers"))
        self._set_text(self.function_buf, data.get("code", ""))

    def _new_function(self, _=None):
        self.selected_function_id = None
        self.function_name_entry.set_text("")
        self._set_text(self.function_buf, "")

    def _save_function(self, _=None):
        name = self.function_name_entry.get_text().strip() or "Table Helpers"
        code = self._get_text(self.function_buf)

        if self.selected_function_id:
            item = table_lab.update_function(self.selected_function_id, name, code)
        else:
            item = table_lab.add_function(name, code)

        self.selected_function_id = item.get("id")
        self._refresh_function_list()
        self.status_lbl.set_text("✅ Table helpers saved.")

    def _delete_function(self, _=None):
        if not self.selected_function_id:
            return

        table_lab.remove_function(self.selected_function_id)
        self.selected_function_id = None
        self._refresh_function_list()
        self._load_first_function()
        self.status_lbl.set_text("Table helpers deleted.")

    def _load_default_helpers(self, _=None):
        self.function_name_entry.set_text("Table Helpers")
        self._set_text(self.function_buf, table_lab.DEFAULT_FUNCTIONS)
        self.status_lbl.set_text("Default Table Helpers loaded.")

    # ── Examples ────────────────────────────────────────────────────────────

    def _load_example_caller(self, _=None):
        self._set_text(self.caller_buf, EXAMPLE_CALLER, mark=True)
        self._parse_columns_from_caller()

    def _load_example_original(self, _=None):
        self._set_text(self.original_buf, EXAMPLE_OUTPUT, mark=True)
        self._parse_original_rows()

    # ── Columns ─────────────────────────────────────────────────────────────

    def _selected_column_iter(self):
        selection = self.column_tree.get_selection()
        model, tree_iter = selection.get_selected()
        return model, tree_iter

    def _update_column_controls(self):
        if not hasattr(self, "width_spin"):
            return

        model, tree_iter = self._selected_column_iter()
        has_selection = tree_iter is not None

        self._syncing_column_controls = True
        self.width_spin.set_sensitive(has_selection)
        self.align_combo.set_sensitive(has_selection)

        if has_selection:
            self.width_spin.set_value(int(model[tree_iter][1]))
            align = str(model[tree_iter][2])
            self.align_combo.set_active_id(align if align in ("<", "^", ">") else "<")

        self._syncing_column_controls = False

    def _on_column_selection_changed(self, *_):
        self._update_column_controls()

    def _on_width_spin_changed(self, spin):
        if self._syncing_column_controls:
            return

        model, tree_iter = self._selected_column_iter()

        if tree_iter is None:
            return

        model[tree_iter][1] = int(spin.get_value())
        self._build_preview()
        self._mark_dirty()

    def _on_align_changed(self, combo):
        if self._syncing_column_controls:
            return

        model, tree_iter = self._selected_column_iter()

        if tree_iter is None:
            return

        align = combo.get_active_id() or "<"
        model[tree_iter][2] = align
        self._build_preview()
        self._mark_dirty()

    def _cycle_align(self, direction):
        order = ["<", "^", ">"]
        current = self.align_combo.get_active_id() or "<"

        try:
            index = order.index(current)
        except ValueError:
            index = 0

        self.align_combo.set_active_id(order[(index + direction) % len(order)])

    def _on_tree_cell_edited(self, _renderer, path, new_text, model_index):
        try:
            if model_index == 1:
                self.column_store[path][model_index] = max(1, int(new_text.strip()))
            elif model_index == 2:
                align = new_text.strip()
                self.column_store[path][model_index] = align if align in ("<", "^", ">") else "<"
            else:
                self.column_store[path][model_index] = new_text.strip() or "Column"
        except Exception:
            return

        self._update_column_controls()
        self._build_preview()
        self._mark_dirty()

    def _on_columns_changed(self, *_):
        if self._loading:
            return

        self._build_preview()
        self._mark_dirty()

    def _add_column(self, _=None, title="-", width=10, align="<"):
        """
        Add a blank placeholder column.

        This avoids the confusing behaviour where a new column looks like it
        reused an existing field. The user can then rename it and adjust width
        / alignment using the controls.
        """
        tree_iter = self.column_store.append([title or "-", int(width), align or "<"])
        path = self.column_store.get_path(tree_iter)

        self.column_tree.get_selection().select_iter(tree_iter)
        self.column_tree.scroll_to_cell(path, None, False, 0, 0)

        self._update_column_controls()
        self._build_preview()
        self._mark_dirty()
        self.status_lbl.set_text("Added blank column placeholder. Rename '-' when ready.")

    def _remove_selected_column(self, _=None):
        model, tree_iter = self._selected_column_iter()

        if tree_iter is None:
            return

        model.remove(tree_iter)
        self._build_preview()
        self._mark_dirty()
        self._update_column_controls()

    def _move_selected_column(self, direction):
        model, tree_iter = self._selected_column_iter()

        if tree_iter is None:
            return

        path = model.get_path(tree_iter)
        index = path.get_indices()[0]
        new_index = index + direction

        if new_index < 0 or new_index >= len(model):
            return

        other_iter = model.get_iter(Gtk.TreePath.new_from_string(str(new_index)))
        model.swap(tree_iter, other_iter)

        self.column_tree.get_selection().select_path(Gtk.TreePath.new_from_string(str(new_index)))
        self._build_preview()
        self._mark_dirty()

    def _read_columns(self):
        columns = []

        for row in self.column_store:
            title = str(row[0]).strip() or "Column"
            width = int(row[1]) if row[1] else 10
            align = str(row[2]).strip()

            if align not in ("<", "^", ">"):
                align = "<"

            columns.append((title, width, align))

        return columns

    def _set_columns(self, columns):
        self._loading = True
        self.column_store.clear()

        for col in columns:
            if len(col) == 3:
                title, width, align = col
            else:
                title, width = col
                align = "<"

            self.column_store.append([str(title), int(width), align])

        self._loading = False

        first = self.column_store.get_iter_first()
        if first is not None:
            self.column_tree.get_selection().select_iter(first)

        self._build_preview()
        self._mark_dirty()

    def _apply_preset(self, mode):
        columns = self._read_columns()

        if not columns:
            return

        adjusted = []

        for title, width, align in columns:
            if mode == "compact":
                width = max(len(title) + 2, min(width, 14))
            elif mode == "readable":
                width = max(width, len(title) + 4)
            elif mode == "wide":
                width = max(width + 4, len(title) + 6)

            adjusted.append((title, width, align))

        self._set_columns(adjusted)

    def _preview_setting_changed(self):
        if self._loading:
            return

        self._build_preview()
        self._mark_dirty()

    # ── Parsing ─────────────────────────────────────────────────────────────

    def _parse_everything(self, _=None):
        caller = self._get_text(self.caller_buf).strip()
        original = self._get_text(self.original_buf).strip()

        if caller:
            self._parse_columns_from_caller()
            self._parse_original_rows()
        elif original:
            self._infer_from_original_output()
        else:
            self._show_info("Paste either Table Caller code or Original Output first.")
            return

        self._build_preview()
        self._generate_replacement_code()

    def _parse_columns_from_caller(self, _=None):
        caller = self._get_text(self.caller_buf)
        columns = []

        match = re.search(r"columns\s*=\s*(\[[\s\S]*?\])", caller)

        if match:
            raw = match.group(1)
            try:
                parsed = ast.literal_eval(raw)
                for item in parsed:
                    if isinstance(item, tuple) and len(item) in (2, 3):
                        title = str(item[0])
                        width = int(item[1])
                        align = item[2] if len(item) == 3 else "<"
                        align = align if align in ("<", "^", ">") else "<"
                        columns.append((title, width, align))
            except Exception:
                pass

        if not columns:
            tuple_re = re.compile(
                r"\(\s*[\"']([^\"]+?)[\"']\s*,\s*(\d+)(?:\s*,\s*[\"']([<^>])[\"'])?\s*\)"
            )

            for title, width, align in tuple_re.findall(caller):
                columns.append((title, int(width), align or "<"))

        if not columns:
            self._show_info("No columns found. Paste a caller containing columns = [...] or add columns manually.")
            return

        self.source_column_defs = [
            (str(title), int(width), str(align if align in ("<", "^", ">") else "<"))
            for title, width, align in columns
        ]

        self._set_columns(columns)
        self._parse_original_rows()
        self._build_preview()
        self.status_lbl.set_text(f"✅ Parsed {len(columns)} source column(s).")

    def _column_key(self, name):
        return re.sub(r"\s+", " ", str(name)).strip().lower()

    def _detect_header_chunks(self, header_line):
        """
        Split a fixed-width table header into column titles.

        Uses 2+ spaces as the separator, so names like 'IP Address'
        stay as one column.
        """
        indent = len(header_line) - len(header_line.lstrip(" "))
        body = header_line[indent:].rstrip()

        chunks = []
        for match in re.finditer(r"\S(?:.*?\S)?(?=\s{2,}|$)", body):
            title = match.group(0).strip()
            if title:
                chunks.append((title, indent + match.start()))

        return chunks

    def _infer_from_original_output(self, _=None):
        """
        Infer columns and rows directly from pasted terminal output.

        This lets the user paste only the Original Output/Original Version,
        without needing Table Caller code.
        """
        original = strip_ansi(self._get_text(self.original_buf)).replace("\t", "    ")

        self.prefix_lines = []
        self.parsed_rows = []

        if not original.strip():
            self.status_lbl.set_text("Paste Original Output first.")
            return

        lines = original.splitlines()
        separator_index = None

        for index, line in enumerate(lines):
            if re.match(r"^\s*-{5,}\s*$", line):
                separator_index = index
                break

        if separator_index is None or separator_index == 0:
            self.status_lbl.set_text("Could not find a header + ----- separator in Original Output.")
            return

        header_index = separator_index - 1
        header_line = lines[header_index]
        self.prefix_lines = lines[:header_index]

        detected = self._detect_header_chunks(header_line)

        if not detected:
            self.status_lbl.set_text("Could not detect columns from the Original Output header.")
            return

        data_lines = [
            line for line in lines[separator_index + 1:]
            if line.strip()
        ]

        max_len = max(
            [len(header_line.rstrip())]
            + [len(line.rstrip()) for line in data_lines]
            + [len(lines[separator_index].rstrip())]
        )

        inferred_columns = []

        for index, (title, start) in enumerate(detected):
            if index + 1 < len(detected):
                end = detected[index + 1][1]
            else:
                end = max_len

            width = max(len(title) + 2, end - start)

            values = []
            for raw in data_lines:
                value = raw[start:end].strip() if end is not None else raw[start:].strip()
                if value:
                    values.append(value)

            if values:
                width = max(width, max(len(v) + 2 for v in values))

            all_numeric = bool(values) and all(v.replace(".", "", 1).isdigit() for v in values)
            align = "^" if all_numeric else "<"

            inferred_columns.append((title, width, align))

        self.source_column_defs = [
            (title, width, align)
            for title, width, align in inferred_columns
        ]

        self._set_columns(inferred_columns)

        # Build row maps by original title.
        for raw in data_lines:
            row_map = {}

            for index, (title, start) in enumerate(detected):
                if index + 1 < len(detected):
                    end = detected[index + 1][1]
                else:
                    end = None

                value = raw[start:end].strip() if end is not None else raw[start:].strip()
                row_map[str(title)] = value

            if any(str(value).strip() for value in row_map.values()):
                self.parsed_rows.append(row_map)

        self._build_preview()
        self._generate_replacement_code()
        self._mark_dirty()
        self.status_lbl.set_text(
            f"✅ Inferred {len(inferred_columns)} column(s) and {len(self.parsed_rows)} row(s) from Original Output."
        )


    def _parse_original_rows(self, _=None):
        original = strip_ansi(self._get_text(self.original_buf)).replace("\t", "    ")
        source_columns = getattr(self, "source_column_defs", []) or self._read_columns()

        if not source_columns and original.strip():
            self._infer_from_original_output()
            return

        self.prefix_lines = []
        self.parsed_rows = []

        if not original.strip() or not source_columns:
            self.status_lbl.set_text("Paste Original Output and parse columns first.")
            return

        lines = original.splitlines()
        separator_index = None

        for index, line in enumerate(lines):
            if re.match(r"^\s*-{5,}\s*$", line):
                separator_index = index
                break

        if separator_index is None:
            self.status_lbl.set_text("Could not find a separator line like ----- in Original Output.")
            return

        header_index = max(0, separator_index - 1)
        self.prefix_lines = lines[:header_index]

        data_lines = [
            line for line in lines[separator_index + 1:]
            if line.strip()
        ]

        detected = self._detect_header_chunks(lines[header_index])
        detected_titles = [title for title, _start in detected]

        # Best path: parse using header positions.
        if detected:
            for raw in data_lines:
                row_map = {}

                for index, (title, start) in enumerate(detected):
                    if index + 1 < len(detected):
                        end = detected[index + 1][1]
                    else:
                        end = None

                    row_map[str(title)] = raw[start:end].strip() if end is not None else raw[start:].strip()

                if any(str(value).strip() for value in row_map.values()):
                    self.parsed_rows.append(row_map)

            self.source_column_defs = [
                (title, width, align)
                for title, width, align in source_columns
                if title in detected_titles
            ] or source_columns

        else:
            indent = int(self.indent_spin.get_value())
            gap = int(self.gap_spin.get_value())

            for raw in data_lines:
                line = raw[indent:] if raw.startswith(" " * indent) else raw.lstrip()
                row_map = {}
                pos = 0

                for title, width, _align in source_columns:
                    row_map[str(title)] = line[pos:pos + int(width)].strip()
                    pos += int(width) + gap

                if any(str(value).strip() for value in row_map.values()):
                    self.parsed_rows.append(row_map)

        self.status_lbl.set_text(f"✅ Parsed {len(self.parsed_rows)} row(s).")
        self._build_preview()
        self._mark_dirty()

    # ── Preview / generated code ────────────────────────────────────────────

    def _render_table(self):
        columns = self._read_columns()

        if not columns:
            return "No columns yet. Paste Original Output and click Infer Table, or paste Table Caller and click 1 Parse."

        indent = " " * int(self.indent_spin.get_value())
        gap = " " * int(self.gap_spin.get_value())
        sep_char = self.separator_entry.get_text()[:1] or "-"

        lines = []

        for line in self.prefix_lines:
            lines.append(line)

        if lines and lines[-1].strip():
            lines.append("")

        header = indent + gap.join(
            format_cell(title, width, align)
            for title, width, align in columns
        )
        lines.append(header)

        separator_width = sum(width for _title, width, _align in columns)
        separator_width += int(self.gap_spin.get_value()) * max(0, len(columns) - 1)
        lines.append(indent + sep_char * separator_width)

        rows = self.parsed_rows

        if not rows:
            rows = [{str(title): "example" for title, _width, _align in columns}]

        source_titles = [
            str(title)
            for title, _width, _align in (getattr(self, "source_column_defs", []) or columns)
        ]

        for row in rows:
            if isinstance(row, dict):
                lookup = {
                    self._column_key(title): value
                    for title, value in row.items()
                }
            else:
                lookup = {
                    self._column_key(source_titles[index]): value
                    for index, value in enumerate(row)
                    if index < len(source_titles)
                }

            values = []

            for title, _width, _align in columns:
                value = lookup.get(self._column_key(title), "-")
                values.append(value if str(value).strip() else "-")

            lines.append(
                indent + gap.join(
                    format_cell(value, columns[index][1], columns[index][2])
                    for index, value in enumerate(values)
                )
            )

        return "\n".join(lines)

    def _build_preview(self, _=None):
        preview = self._render_table()
        self._set_text(self.preview_buf, preview)

    def _columns_code(self):
        columns = self._read_columns()
        lines = ["columns = ["]

        for title, width, align in columns:
            safe_title = title.replace('"', '\\"')

            if align == "<":
                lines.append(f'    ("{safe_title}", {width}),')
            else:
                lines.append(f'    ("{safe_title}", {width}, "{align}"),')

        lines.append("]")
        return "\n".join(lines)

    def _replace_columns_block(self, caller):
        columns_code = self._columns_code()

        if re.search(r"columns\s*=\s*\[[\s\S]*?\]", caller):
            return re.sub(
                r"columns\s*=\s*\[[\s\S]*?\]",
                columns_code,
                caller,
                count=1
            )

        return columns_code + "\n\n" + caller

    def _replace_format_column_widths(self, caller):
        columns = self._read_columns()

        if not columns:
            return caller

        pattern = re.compile(
            r"format_column\(\s*([^,\n\)]+?)\s*,\s*\d+\s*(?:,\s*([\"'])([<^>])\2\s*)?\)"
        )

        index = {"value": 0}

        def repl(match):
            column = columns[index["value"] % len(columns)]
            index["value"] += 1

            expression = match.group(1).strip()
            width = column[1]
            align = column[2]

            if align == "<":
                return f"format_column({expression}, {width})"

            return f'format_column({expression}, {width}, "{align}")'

        return pattern.sub(repl, caller)

    def _generate_replacement_code(self, _=None):
        caller = self._get_text(self.caller_buf).strip()

        if not caller:
            generated = self._columns_code()
        else:
            generated = self._replace_columns_block(caller)
            generated = self._replace_format_column_widths(generated)

        self._set_text(self.generated_buf, generated)
        self.notebook.set_current_page(2)
        self.status_lbl.set_text("✅ Replacement code generated.")
        self._mark_dirty()

    # ── Help ────────────────────────────────────────────────────────────────

    def _show_help(self, _=None):
        self._show_info(
            "Best workflow:\n\n"
            "1. Paste the SentinelIR table caller code into Table Caller.\n"
            "2. Paste the old terminal output into Original Output.\n"
            "3. Click 1 Parse.\n"
            "4. Go to 2 Tune and adjust widths/alignment.\n"
            "5. Drag columns to reorder them.\n"
            "6. Click 3 Generate Code.\n"
            "7. Copy Generated Code and paste it back into SentinelIR.\n\n"
            "Extra gap = extra spaces inserted between preview columns. "
            "Usually keep it at 0 unless the table looks too cramped.",
            title="How to use Table Lab"
        )
