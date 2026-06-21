"""Table Lab — CLI table spacing designer/debugger."""
import ast
import os
import re
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango

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
    return ANSI_RE.sub("", text)


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
        self.selected_function_id = None
        self.parsed_rows = []
        self.prefix_lines = []

        # Deliberately not transient.
        # Table Lab should survive when the main window is hidden,
        # like the Checklist window.

        self.set_default_size(1180, 780)
        self.set_size_request(760, 520)

        self._apply_css()
        self._build()
        self._refresh_function_list()
        self.connect("delete-event", self._on_close)
        self.show_all()

    def _on_toggle_main_window(self, btn):
        parent = getattr(self, "parent_window", None)

        if parent is None:
            btn.set_active(False)
            return

        if btn.get_active():
            parent.hide()
            btn.set_label("👁 Show Main Window")
            self.present()
        else:
            parent.show()
            parent.present()
            btn.set_label("🙈 Hide Main Window")

    def _restore_main_window_if_hidden(self):
        parent = getattr(self, "parent_window", None)

        if parent is not None and not parent.get_visible():
            parent.show()
            parent.present()

    def _on_close(self, _window, _event):
        self._restore_main_window_if_hidden()
        return False


    # ── UI helpers ──────────────────────────────────────────────────────────

    def _apply_css(self):
        css = b"""
        .lab-section-title {
            font-weight: bold;
            font-size: 12px;
        }
        .lab-muted {
            opacity: 0.62;
            font-size: 10px;
        }
        .lab-toolbar {
            background: alpha(white, 0.04);
            border-bottom: 1px solid alpha(white, 0.08);
            padding: 8px;
        }
        .lab-code {
            font-family: monospace;
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

    def _label(self, text, muted=False):
        lbl = Gtk.Label(label=text)
        lbl.set_halign(Gtk.Align.START)
        lbl.get_style_context().add_class("lab-muted" if muted else "lab-section-title")
        return lbl

    def _text_view(self, monospace=True, editable=True):
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)

        buf = Gtk.TextBuffer()
        view = Gtk.TextView(buffer=buf)
        view.set_wrap_mode(Gtk.WrapMode.NONE)
        view.set_editable(editable)

        if monospace:
            view.set_monospace(True)
            view.get_style_context().add_class("lab-code")

        scroll.add(view)
        return scroll, view, buf

    def _get_text(self, buf):
        start, end = buf.get_bounds()
        return buf.get_text(start, end, False)

    def _set_text(self, buf, text):
        buf.set_text(text or "")

    def _copy_text(self, text, label="Copied to clipboard."):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(text or "", -1)
        self.status_lbl.set_text("✅ " + label)

    def _info(self, message, title="Table Lab"):
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

    # ── Build layout ────────────────────────────────────────────────────────

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)

        toolbar = Gtk.Box(spacing=8)
        toolbar.get_style_context().add_class("lab-toolbar")

        parse_btn = Gtk.Button(label="🔍 Parse Caller Columns")
        parse_btn.set_tooltip_text("Read the columns = [...] block from the Table Caller box")
        parse_btn.connect("clicked", self._parse_columns_from_caller)
        toolbar.pack_start(parse_btn, False, False, 0)

        preview_btn = Gtk.Button(label="👀 Build Updated Preview")
        preview_btn.connect("clicked", self._build_preview)
        toolbar.pack_start(preview_btn, False, False, 0)

        code_btn = Gtk.Button(label="⚙ Generate Replacement Code")
        code_btn.connect("clicked", self._generate_replacement_code)
        toolbar.pack_start(code_btn, False, False, 0)

        copy_code_btn = Gtk.Button(label="📋 Copy Replacement Code")
        copy_code_btn.connect("clicked", lambda _: self._copy_text(
            self._get_text(self.generated_buf),
            "replacement code copied."
        ))
        toolbar.pack_start(copy_code_btn, False, False, 0)

        self.main_win_btn = Gtk.ToggleButton(label="🙈 Hide Main Window")
        self.main_win_btn.set_tooltip_text("Hide/show the main Multi-Commit window while keeping Table Lab open")
        self.main_win_btn.connect("toggled", self._on_toggle_main_window)
        toolbar.pack_end(self.main_win_btn, False, False, 0)

        self.status_lbl = Gtk.Label(label="Ready")
        self.status_lbl.set_halign(Gtk.Align.START)
        toolbar.pack_end(self.status_lbl, True, True, 0)

        root.pack_start(toolbar, False, False, 0)

        vertical = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        vertical.set_position(360)
        root.pack_start(vertical, True, True, 0)

        top_and_middle = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        top_and_middle.set_position(245)
        vertical.pack1(top_and_middle, resize=True, shrink=False)

        top = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        top.set_position(560)
        top_and_middle.pack1(top, resize=True, shrink=False)

        top.pack1(self._build_functions_panel(), resize=True, shrink=False)
        top.pack2(self._build_caller_panel(), resize=True, shrink=False)

        middle = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        middle.set_position(560)
        top_and_middle.pack2(middle, resize=True, shrink=False)

        middle.pack1(self._build_original_panel(), resize=True, shrink=False)
        middle.pack2(self._build_preview_panel(), resize=True, shrink=False)

        bottom = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bottom.set_border_width(8)
        bottom.pack_start(self._label("Generated Replacement Code"), False, False, 0)
        generated_scroll, self.generated_view, self.generated_buf = self._text_view()
        bottom.pack_start(generated_scroll, True, True, 0)
        vertical.pack2(bottom, resize=True, shrink=False)

    def _build_functions_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)

        row = Gtk.Box(spacing=6)
        row.pack_start(self._label("Functions Library"), True, True, 0)

        new_btn = Gtk.Button(label="New")
        new_btn.connect("clicked", self._new_function)
        row.pack_end(new_btn, False, False, 0)

        save_btn = Gtk.Button(label="Save")
        save_btn.connect("clicked", self._save_function)
        row.pack_end(save_btn, False, False, 0)

        delete_btn = Gtk.Button(label="Delete")
        delete_btn.connect("clicked", self._delete_function)
        row.pack_end(delete_btn, False, False, 0)

        box.pack_start(row, False, False, 0)

        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split.set_position(190)

        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        self.function_list = Gtk.ListBox()
        self.function_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.function_list.connect("row-selected", self._on_function_selected)

        list_scroll = Gtk.ScrolledWindow()
        list_scroll.set_min_content_width(160)
        list_scroll.add(self.function_list)
        left.pack_start(list_scroll, True, True, 0)

        example_btn = Gtk.Button(label="Load Example")
        example_btn.connect("clicked", self._load_example_functions)
        left.pack_start(example_btn, False, False, 0)

        split.pack1(left, resize=False, shrink=False)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)

        self.function_name_entry = Gtk.Entry()
        self.function_name_entry.set_placeholder_text("Function snippet name")
        right.pack_start(self.function_name_entry, False, False, 0)

        function_scroll, self.function_view, self.function_buf = self._text_view()
        right.pack_start(function_scroll, True, True, 0)

        copy_btn = Gtk.Button(label="📋 Copy Functions")
        copy_btn.connect("clicked", lambda _: self._copy_text(
            self._get_text(self.function_buf),
            "functions copied."
        ))
        right.pack_start(copy_btn, False, False, 0)

        split.pack2(right, resize=True, shrink=False)

        box.pack_start(split, True, True, 0)
        return box

    def _build_caller_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)

        row = Gtk.Box(spacing=6)
        row.pack_start(self._label("Table Caller"), True, True, 0)

        load_btn = Gtk.Button(label="Load Example")
        load_btn.connect("clicked", self._load_example_caller)
        row.pack_end(load_btn, False, False, 0)

        copy_btn = Gtk.Button(label="Copy")
        copy_btn.connect("clicked", lambda _: self._copy_text(
            self._get_text(self.caller_buf),
            "caller copied."
        ))
        row.pack_end(copy_btn, False, False, 0)

        box.pack_start(row, False, False, 0)

        caller_scroll, self.caller_view, self.caller_buf = self._text_view()
        box.pack_start(caller_scroll, True, True, 0)
        return box

    def _build_original_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)

        row = Gtk.Box(spacing=6)
        row.pack_start(self._label("Original Output"), True, True, 0)

        load_btn = Gtk.Button(label="Load Example")
        load_btn.connect("clicked", self._load_example_original)
        row.pack_end(load_btn, False, False, 0)

        parse_btn = Gtk.Button(label="Parse Rows")
        parse_btn.connect("clicked", self._parse_original_rows)
        row.pack_end(parse_btn, False, False, 0)

        box.pack_start(row, False, False, 0)

        original_scroll, self.original_view, self.original_buf = self._text_view(editable=True)
        box.pack_start(original_scroll, True, True, 0)
        return box

    def _build_preview_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.set_border_width(8)

        box.pack_start(self._label("Updated Preview"), False, False, 0)

        controls = Gtk.Grid(column_spacing=8, row_spacing=4)
        controls.set_margin_bottom(4)

        controls.attach(Gtk.Label(label="Indent"), 0, 0, 1, 1)
        self.indent_spin = Gtk.SpinButton()
        self.indent_spin.set_range(0, 12)
        self.indent_spin.set_increments(1, 1)
        self.indent_spin.set_value(3)
        self.indent_spin.connect("value-changed", lambda _: self._build_preview())
        controls.attach(self.indent_spin, 1, 0, 1, 1)

        controls.attach(Gtk.Label(label="Column gap"), 2, 0, 1, 1)
        self.gap_spin = Gtk.SpinButton()
        self.gap_spin.set_range(0, 8)
        self.gap_spin.set_increments(1, 1)
        self.gap_spin.set_value(0)
        self.gap_spin.connect("value-changed", lambda _: self._build_preview())
        controls.attach(self.gap_spin, 3, 0, 1, 1)

        controls.attach(Gtk.Label(label="Separator"), 4, 0, 1, 1)
        self.separator_entry = Gtk.Entry()
        self.separator_entry.set_width_chars(3)
        self.separator_entry.set_text("-")
        self.separator_entry.connect("changed", lambda _: self._build_preview())
        controls.attach(self.separator_entry, 5, 0, 1, 1)

        compact_btn = Gtk.Button(label="Compact")
        compact_btn.connect("clicked", lambda _: self._apply_preset("compact"))
        controls.attach(compact_btn, 6, 0, 1, 1)

        readable_btn = Gtk.Button(label="Readable")
        readable_btn.connect("clicked", lambda _: self._apply_preset("readable"))
        controls.attach(readable_btn, 7, 0, 1, 1)

        wide_btn = Gtk.Button(label="Wide")
        wide_btn.connect("clicked", lambda _: self._apply_preset("wide"))
        controls.attach(wide_btn, 8, 0, 1, 1)

        box.pack_start(controls, False, False, 0)

        column_row = Gtk.Box(spacing=6)
        column_row.pack_start(self._label("Column Editor", muted=True), True, True, 0)

        add_btn = Gtk.Button(label="+ Column")
        add_btn.connect("clicked", self._add_column)
        column_row.pack_end(add_btn, False, False, 0)

        remove_btn = Gtk.Button(label="Remove")
        remove_btn.connect("clicked", self._remove_selected_column)
        column_row.pack_end(remove_btn, False, False, 0)

        box.pack_start(column_row, False, False, 0)

        self.column_store = Gtk.ListStore(str, int, str)
        self.column_tree = Gtk.TreeView(model=self.column_store)
        self.column_tree.set_headers_visible(True)

        self._add_text_column("Title", 0)
        self._add_text_column("Width", 1)
        self._add_text_column("Align (< ^ >)", 2)

        column_scroll = Gtk.ScrolledWindow()
        column_scroll.set_min_content_height(110)
        column_scroll.add(self.column_tree)
        box.pack_start(column_scroll, False, False, 0)

        preview_scroll, self.preview_view, self.preview_buf = self._text_view(editable=False)
        box.pack_start(preview_scroll, True, True, 0)
        return box

    def _add_text_column(self, title, index):
        renderer = Gtk.CellRendererText()
        renderer.set_property("editable", True)
        renderer.connect("edited", self._on_column_edited, index)

        column = Gtk.TreeViewColumn(title, renderer, text=index)
        column.set_resizable(True)
        column.set_expand(True)
        self.column_tree.append_column(column)

    # ── Function library ────────────────────────────────────────────────────

    def _refresh_function_list(self):
        for child in self.function_list.get_children():
            self.function_list.remove(child)

        for item in table_lab.list_functions():
            row = Gtk.ListBoxRow()
            row.function_id = item.get("id")
            row.function_data = item

            label = Gtk.Label(label=item.get("name", "Untitled Functions"))
            label.set_halign(Gtk.Align.START)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_margin_top(5)
            label.set_margin_bottom(5)
            label.set_margin_start(5)
            label.set_margin_end(5)

            row.add(label)
            self.function_list.add(row)

        self.function_list.show_all()

    def _on_function_selected(self, _listbox, row):
        if row is None or not hasattr(row, "function_data"):
            return

        data = row.function_data
        self.selected_function_id = data.get("id")
        self.function_name_entry.set_text(data.get("name", ""))
        self._set_text(self.function_buf, data.get("code", ""))

    def _new_function(self, _=None):
        self.selected_function_id = None
        self.function_name_entry.set_text("")
        self._set_text(self.function_buf, "")
        self.status_lbl.set_text("New function snippet ready.")

    def _save_function(self, _=None):
        name = self.function_name_entry.get_text().strip() or "Untitled Functions"
        code = self._get_text(self.function_buf)

        if self.selected_function_id:
            item = table_lab.update_function(self.selected_function_id, name, code)
        else:
            item = table_lab.add_function(name, code)
            self.selected_function_id = item.get("id")

        self._refresh_function_list()
        self.status_lbl.set_text("✅ Function snippet saved.")

    def _delete_function(self, _=None):
        if not self.selected_function_id:
            return

        table_lab.remove_function(self.selected_function_id)
        self.selected_function_id = None
        self.function_name_entry.set_text("")
        self._set_text(self.function_buf, "")
        self._refresh_function_list()
        self.status_lbl.set_text("Deleted function snippet.")

    # ── Examples ────────────────────────────────────────────────────────────

    def _load_example_functions(self, _=None):
        self.function_name_entry.set_text("SentinelIR table helpers")
        self._set_text(self.function_buf, table_lab.DEFAULT_FUNCTIONS)
        self.status_lbl.set_text("Loaded helper function example.")

    def _load_example_caller(self, _=None):
        self._set_text(self.caller_buf, EXAMPLE_CALLER)
        self._parse_columns_from_caller()

    def _load_example_original(self, _=None):
        self._set_text(self.original_buf, EXAMPLE_OUTPUT)
        self._parse_original_rows()

    # ── Column editor ───────────────────────────────────────────────────────

    def _on_column_edited(self, _renderer, path, new_text, index):
        try:
            if index == 1:
                self.column_store[path][index] = max(1, int(new_text.strip()))
            elif index == 2:
                val = new_text.strip()
                self.column_store[path][index] = val if val in ("<", "^", ">") else "<"
            else:
                self.column_store[path][index] = new_text
        except Exception:
            return

        self._build_preview()

    def _add_column(self, _=None, title="New Column", width=12, align="<"):
        self.column_store.append([title, int(width), align])
        self._build_preview()

    def _remove_selected_column(self, _=None):
        selection = self.column_tree.get_selection()
        model, tree_iter = selection.get_selected()

        if tree_iter is not None:
            model.remove(tree_iter)
            self._build_preview()

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
        self.column_store.clear()

        for col in columns:
            if len(col) == 3:
                title, width, align = col
            else:
                title, width = col
                align = "<"

            self.column_store.append([str(title), int(width), align])

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
        self._build_preview()

    # ── Parsing ─────────────────────────────────────────────────────────────

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
                        columns.append((title, width, align))
            except Exception:
                pass

        if not columns:
            tuple_re = re.compile(
                r"\(\s*[\"']([^\"']+)[\"']\s*,\s*(\d+)(?:\s*,\s*[\"']([<^>])[\"'])?\s*\)"
            )

            for title, width, align in tuple_re.findall(caller):
                columns.append((title, int(width), align or "<"))

        if not columns:
            self._info("No columns found. Add columns manually or paste a caller with columns = [...].")
            return

        self._set_columns(columns)
        self.status_lbl.set_text(f"✅ Parsed {len(columns)} column(s) from caller.")
        self._parse_original_rows()
        self._build_preview()
        self._generate_replacement_code()

    def _parse_original_rows(self, _=None):
        original = strip_ansi(self._get_text(self.original_buf)).replace("\t", "    ")
        columns = self._read_columns()

        self.prefix_lines = []
        self.parsed_rows = []

        if not original.strip() or not columns:
            return

        lines = original.splitlines()
        sep_index = None

        for i, line in enumerate(lines):
            if re.match(r"^\s*-{5,}\s*$", line):
                sep_index = i
                break

        if sep_index is None:
            self.status_lbl.set_text("Could not find separator line in original output.")
            return

        header_index = max(0, sep_index - 1)
        self.prefix_lines = lines[:header_index]

        indent = int(self.indent_spin.get_value())
        gap = int(self.gap_spin.get_value())

        for raw in lines[sep_index + 1:]:
            if not raw.strip():
                continue

            line = raw[indent:] if raw.startswith(" " * indent) else raw.lstrip()
            values = []
            pos = 0

            for _title, width, _align in columns:
                values.append(line[pos:pos + width].strip())
                pos += width + gap

            if any(values):
                self.parsed_rows.append(values)

        self.status_lbl.set_text(f"Parsed {len(self.parsed_rows)} row(s) from original output.")

    # ── Preview / code generation ───────────────────────────────────────────

    def _render_table(self):
        columns = self._read_columns()

        if not columns:
            return "No columns yet. Paste a caller and click Parse Caller Columns, or add columns manually."

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
            rows = [[title for title, _width, _align in columns]]

        for row in rows:
            padded = []
            for i, (_title, _width, _align) in enumerate(columns):
                padded.append(row[i] if i < len(row) else "")

            lines.append(
                indent + gap.join(
                    format_cell(value, columns[i][1], columns[i][2])
                    for i, value in enumerate(padded)
                )
            )

        return "\n".join(lines)

    def _build_preview(self, _=None):
        self._parse_original_rows()
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
            col = columns[index["value"] % len(columns)]
            index["value"] += 1

            expr = match.group(1).strip()
            width = col[1]
            align = col[2]

            if align == "<":
                return f"format_column({expr}, {width})"

            return f'format_column({expr}, {width}, "{align}")'

        return pattern.sub(repl, caller)

    def _generate_replacement_code(self, _=None):
        caller = self._get_text(self.caller_buf).strip()

        if not caller:
            generated = self._columns_code()
        else:
            generated = self._replace_columns_block(caller)
            generated = self._replace_format_column_widths(generated)

        self._set_text(self.generated_buf, generated)
        self.status_lbl.set_text("✅ Replacement code generated.")
