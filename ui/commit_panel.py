"""Right panel — full git workflow + branch/stash/pull/diff/notes tools."""
import os
import subprocess
from datetime import datetime
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango
from core import git_ops, settings, project_manager
from core import notify, activity
from core.notes import get as get_note, save_note
from ui.branch_panel import BranchPanel
from ui.stash_panel import StashPanel
from ui.pull_panel import PullPanel
from ui.tag_panel import TagPanel

COMMIT_TEMPLATES = [
    ("feat",     "feat: "),
    ("fix",      "fix: "),
    ("docs",     "docs: "),
    ("style",    "style: "),
    ("refactor", "refactor: "),
    ("test",     "test: "),
    ("chore",    "chore: "),
    ("perf",     "perf: "),
    ("ci",       "ci: "),
    ("revert",   "revert: "),
]

class CommitPanel(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.project_path = None
        self._note_save_timeout = None
        self._apply_css()
        self._build()

    def _apply_css(self):
        css = b"""
        .commit-header { padding: 12px 16px 8px 16px; border-bottom: 1px solid alpha(white,0.08); }
        .step-card {
            background: alpha(white, 0.04); border-radius: 6px;
            border: 1px solid alpha(white, 0.08); padding: 10px; margin: 4px 0;
        }
        .tool-card {
            background: alpha(white, 0.03); border-radius: 6px;
            border: 1px solid alpha(white, 0.06); margin: 4px 0;
        }
        .notes-view {
            font-family: sans-serif; font-size: 12px;
            background: alpha(#f39c12, 0.06);
        }
        .step-title { font-size: 12px; font-weight: bold; opacity: 0.7; }
        .result-ok   { color: #2ecc71; font-size: 11px; }
        .result-fail { color: #e74c3c; font-size: 11px; }
        .history-view { font-size: 11px; font-family: monospace; opacity: 0.8; }
        .output-view  { font-size: 11px; font-family: monospace; }
        .shortcut-hint { font-size: 10px; opacity: 0.45; }
        .quick-commit-btn {
            background: linear-gradient(135deg, #c0392b, #922b21);
            color: white; font-weight: bold;
            border-radius: 6px; padding: 6px 16px; border: none;
        }
        .remote-auth-btn { color: #3498db; }
        .template-btn {
            font-size: 10px; padding: 2px 6px;
            border-radius: 3px; border: 1px solid alpha(white,0.15);
        }
                .commit-validator-neutral {
            background: alpha(#ffffff, 0.04);
            color: alpha(#ffffff, 0.65);
            border-left: 2px solid alpha(#ffffff, 0.18);
            padding: 4px 6px;
            border-radius: 4px;
        }
        .commit-validator-good {
            background: alpha(#2ecc71, 0.10);
            color: #c9f7d8;
            border-left: 2px solid alpha(#2ecc71, 0.45);
            padding: 4px 6px;
            border-radius: 4px;
        }
        .commit-validator-warn {
            background: alpha(#f1c40f, 0.10);
            color: #fff0b8;
            border-left: 2px solid alpha(#f1c40f, 0.45);
            padding: 4px 6px;
            border-radius: 4px;
        }
        .commit-validator-bad {
            background: alpha(#e74c3c, 0.10);
            color: #ffd0cc;
            border-left: 2px solid alpha(#e74c3c, 0.45);
            padding: 4px 6px;
            border-radius: 4px;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            __import__("gi.repository", fromlist=["Gdk"]).Gdk.Screen.get_default(),
            provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build(self):
        # ── HEADER ──
        hdr = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        hdr.get_style_context().add_class("commit-header")

        title_row = Gtk.Box(spacing=8)
        self.project_label = Gtk.Label()
        self.project_label.set_markup("<b>No project selected</b>")
        self.project_label.set_halign(Gtk.Align.START)
        title_row.pack_start(self.project_label, True, True, 0)

        self.quick_btn = Gtk.Button(label="⚡ Quick Commit  Ctrl+Enter")
        self.quick_btn.get_style_context().add_class("quick-commit-btn")
        self.quick_btn.set_tooltip_text("git add . → commit → push all")
        self.quick_btn.connect("clicked", self._do_quick_commit)
        self.quick_btn.set_sensitive(False)
        title_row.pack_end(self.quick_btn, False, False, 0)
        hdr.pack_start(title_row, False, False, 0)

        meta_row = Gtk.Box(spacing=8)
        self.status_label = Gtk.Label(label="")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_label.get_style_context().add_class("dim-label")
        meta_row.pack_start(self.status_label, True, True, 0)

        for label, attr, cb in [
            ("📜 History", "history_toggle", self._toggle_history),
            ("🔍 Diff",    "diff_toggle",    self._toggle_diff),
        ]:
            btn = Gtk.ToggleButton(label=label)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.connect("toggled", cb)
            setattr(self, attr, btn)
            meta_row.pack_end(btn, False, False, 0)

        hdr.pack_start(meta_row, False, False, 0)
        self.pack_start(hdr, False, False, 0)

        # ── HISTORY REVEALER ──
        self.history_revealer = self._make_revealer(90)
        self.history_view = Gtk.TextView()
        self.history_view.set_editable(False)
        self.history_view.set_wrap_mode(Gtk.WrapMode.NONE)
        self.history_view.get_style_context().add_class("history-view")
        self.history_buf = self.history_view.get_buffer()
        hs = Gtk.ScrolledWindow()
        hs.set_min_content_height(90)
        hs.add(self.history_view)
        self.history_revealer.add(hs)
        self.pack_start(self.history_revealer, False, False, 0)

        # ── DIFF REVEALER ──
        self.diff_revealer = self._make_revealer(150)
        diff_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        diff_hdr = Gtk.Box(spacing=6)
        diff_hdr.set_border_width(6)
        diff_lbl = Gtk.Label()
        diff_lbl.set_markup("<b>Staged + Unstaged Changes</b>")
        diff_lbl.set_halign(Gtk.Align.START)
        diff_hdr.pack_start(diff_lbl, True, True, 0)
        rdiff = Gtk.Button(label="↻")
        rdiff.set_relief(Gtk.ReliefStyle.NONE)
        rdiff.connect("clicked", lambda _: self._load_diff())
        diff_hdr.pack_end(rdiff, False, False, 0)
        diff_box.pack_start(diff_hdr, False, False, 0)
        ds = Gtk.ScrolledWindow()
        ds.set_min_content_height(150)
        self.diff_view = Gtk.TextView()
        self.diff_view.set_editable(False)
        self.diff_view.set_monospace(True)
        self.diff_buf = self.diff_view.get_buffer()
        self.diff_buf.create_tag("add",    foreground="#2ecc71")
        self.diff_buf.create_tag("remove", foreground="#e74c3c")
        self.diff_buf.create_tag("header", foreground="#3498db")
        ds.add(self.diff_view)
        diff_box.pack_start(ds, True, True, 0)
        self.diff_revealer.add(diff_box)
        self.pack_start(self.diff_revealer, False, False, 0)

        # ── SCROLLABLE MAIN ──
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        inner.set_border_width(12)

        # Auto toggles
        auto_box = Gtk.Box(spacing=16)
        auto_box.set_margin_bottom(4)
        self.auto_add_switch  = self._make_switch("Auto git add",  "auto_git_add",  auto_box)
        self.auto_push_switch = self._make_switch("Auto push",     "auto_git_push", auto_box)
        hint = Gtk.Label(label="Ctrl+Enter = quick commit")
        hint.get_style_context().add_class("shortcut-hint")
        auto_box.pack_end(hint, False, False, 0)
        inner.pack_start(auto_box, False, False, 0)

        inner.pack_start(self._step_card_add(),    False, False, 0)
        inner.pack_start(self._step_card_commit(), False, False, 0)
        inner.pack_start(self._step_card_push(),   False, False, 0)
        inner.pack_start(self._step_card_custom(), False, False, 0)

        # ── Collapsible tool cards ──
        for title, rev_attr, builder in [
            ("⬇ Pull / Fetch",   "pull_revealer",   self._build_pull_panel),
            ("⎇ Branch Manager", "branch_revealer", self._build_branch_panel),
            ("🏷 Tag Manager",   "tag_revealer",    self._build_tag_panel),
            ("📦 Stash Manager", "stash_revealer",  self._build_stash_panel),
            ("📝 Project Notes", "notes_revealer",  self._build_notes_panel),
        ]:
            inner.pack_start(
                self._tool_card(title, rev_attr, builder),
                False, False, 0
            )

        # Output log
        out_lbl = Gtk.Label()
        out_lbl.set_markup("<b>Output</b>")
        out_lbl.set_halign(Gtk.Align.START)
        out_lbl.set_margin_top(4)
        inner.pack_start(out_lbl, False, False, 0)

        out_scroll = Gtk.ScrolledWindow()
        out_scroll.set_min_content_height(110)
        self.output_view = Gtk.TextView()
        self.output_view.set_editable(False)
        self.output_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.output_view.get_style_context().add_class("output-view")
        self.output_buf = self.output_view.get_buffer()
        out_scroll.add(self.output_view)
        inner.pack_start(out_scroll, True, True, 0)

        scroll.add(inner)
        self.pack_start(scroll, True, True, 0)
        self.connect("key-press-event", self._on_key_press)

    # ── Revealer / card helpers ──────────────────────────────────────────────

    def _make_revealer(self, min_h=0):
        r = Gtk.Revealer()
        r.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        return r

    def _tool_card(self, title, revealer_attr, content_builder):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        card.get_style_context().add_class("tool-card")

        toggle = Gtk.ToggleButton()
        toggle.set_relief(Gtk.ReliefStyle.NONE)
        hdr = Gtk.Box(spacing=6)
        hdr.set_border_width(8)
        lbl = Gtk.Label()
        lbl.set_markup(f"<b>{title}</b>")
        lbl.set_halign(Gtk.Align.START)
        hdr.pack_start(lbl, True, True, 0)
        arrow = Gtk.Label(label="▸")
        hdr.pack_end(arrow, False, False, 0)
        toggle.add(hdr)
        card.pack_start(toggle, False, False, 0)

        rev = Gtk.Revealer()
        rev.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        setattr(self, revealer_attr, rev)
        rev.add(content_builder())
        card.pack_start(rev, False, False, 0)

        toggle.connect("toggled", lambda b: (
            rev.set_reveal_child(b.get_active()),
            arrow.set_text("▾" if b.get_active() else "▸")
        ))
        return card

    # ── Panel builders ───────────────────────────────────────────────────────

    def _build_pull_panel(self):
        self.pull_panel = PullPanel(on_done=self._on_branch_change)
        return self.pull_panel

    def _build_branch_panel(self):
        self.branch_panel = BranchPanel(on_branch_change=self._on_branch_change)
        return self.branch_panel

    def _build_tag_panel(self):
        self.tag_panel_widget = TagPanel()
        return self.tag_panel_widget

    def _build_stash_panel(self):
        self.stash_panel_widget = StashPanel()
        return self.stash_panel_widget

    def _build_notes_panel(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_border_width(8)

        hint = Gtk.Label(label="Notes are saved automatically per project.")
        hint.get_style_context().add_class("dim-label")
        hint.set_halign(Gtk.Align.START)
        box.pack_start(hint, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(100)
        self.notes_view = Gtk.TextView()
        self.notes_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.notes_view.get_style_context().add_class("notes-view")
        self.notes_buf = self.notes_view.get_buffer()
        self.notes_buf.connect("changed", self._on_notes_changed)
        scroll.add(self.notes_view)
        box.pack_start(scroll, True, True, 0)
        return box

    # ── Step cards ───────────────────────────────────────────────────────────

    def _step_card(self, title):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.get_style_context().add_class("step-card")
        lbl = Gtk.Label(label=title)
        lbl.set_halign(Gtk.Align.START)
        lbl.get_style_context().add_class("step-title")
        card.pack_start(lbl, False, False, 0)
        return card

    def _step_card_add(self):
        card = self._step_card("STEP 1 — git add")
        row = Gtk.Box(spacing=6)
        self.add_entry = Gtk.Entry()
        self.add_entry.set_placeholder_text('Files to stage (default: ".")')
        self.add_entry.set_text(".")
        self.add_entry.connect("activate", self._do_add)
        row.pack_start(self.add_entry, True, True, 0)
        btn = Gtk.Button(label="Stage")
        btn.connect("clicked", self._do_add)
        row.pack_start(btn, False, False, 0)
        card.pack_start(row, False, False, 0)
        self.add_result = self._result_lbl()
        card.pack_start(self.add_result, False, False, 0)
        return card

    def _step_card_commit(self):
        card = self._step_card("STEP 2 — git commit")

        # ── Commit template chips ──
        tmpl_box = Gtk.Box(spacing=4)
        tmpl_box.set_margin_bottom(4)
        tmpl_lbl = Gtk.Label(label="Template:")
        tmpl_lbl.get_style_context().add_class("dim-label")
        tmpl_box.pack_start(tmpl_lbl, False, False, 0)

        for name, prefix in COMMIT_TEMPLATES:
            btn = Gtk.Button(label=name)
            btn.set_relief(Gtk.ReliefStyle.NONE)
            btn.get_style_context().add_class("template-btn")
            btn.set_tooltip_text(f"Prepend '{prefix}'")
            btn.connect("clicked", self._apply_template, prefix)
            tmpl_box.pack_start(btn, False, False, 0)

        card.pack_start(tmpl_box, False, False, 0)

        row = Gtk.Box(spacing=6)
        self.commit_entry = Gtk.Entry()
        self.commit_entry.set_placeholder_text("Commit message…")
        self.commit_entry.connect("activate", self._do_commit)
        self.commit_entry.connect("changed", self._validate_commit_message)
        row.pack_start(self.commit_entry, True, True, 0)
        btn = Gtk.Button(label="Commit")
        btn.connect("clicked", self._do_commit)
        row.pack_start(btn, False, False, 0)
        card.pack_start(row, False, False, 0)

        self.commit_validator_lbl = Gtk.Label(label="Start typing a commit message…")
        self.commit_validator_lbl.set_halign(Gtk.Align.START)
        self.commit_validator_lbl.set_line_wrap(True)
        self.commit_validator_lbl.get_style_context().add_class("commit-validator-neutral")
        card.pack_start(self.commit_validator_lbl, False, False, 0)

        self.commit_result = self._result_lbl()
        card.pack_start(self.commit_result, False, False, 0)
        return card

    def _step_card_push(self):
        card = self._step_card("STEP 3 — git push")
        row = Gtk.Box(spacing=6)
        self.remote_combo = Gtk.ComboBoxText()
        self.remote_combo.append_text("origin")
        self.remote_combo.set_active(0)
        row.pack_start(self.remote_combo, False, False, 0)
        push_btn = Gtk.Button(label="Push")
        push_btn.connect("clicked", self._do_push)
        row.pack_start(push_btn, False, False, 0)
        push_all_btn = Gtk.Button(label="Push All Remotes")
        push_all_btn.connect("clicked", self._do_push_all)
        row.pack_start(push_all_btn, False, False, 0)
        auth_btn = Gtk.Button(label="🔐 Push with Auth")
        auth_btn.get_style_context().add_class("remote-auth-btn")
        auth_btn.connect("clicked", self._do_push_auth_terminal)
        row.pack_end(auth_btn, False, False, 0)
        card.pack_start(row, False, False, 0)
        self.push_result = self._result_lbl()
        card.pack_start(self.push_result, False, False, 0)
        return card

    def _step_card_custom(self):
        card = self._step_card("CUSTOM COMMAND")
        row = Gtk.Box(spacing=6)
        self.custom_entry = Gtk.Entry()
        self.custom_entry.set_placeholder_text("e.g. git stash, git rebase main…")
        self.custom_entry.connect("activate", self._do_custom)
        row.pack_start(self.custom_entry, True, True, 0)
        btn = Gtk.Button(label="Run")
        btn.connect("clicked", self._do_custom)
        row.pack_start(btn, False, False, 0)
        card.pack_start(row, False, False, 0)
        self.custom_result = self._result_lbl()
        card.pack_start(self.custom_result, False, False, 0)
        return card

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _result_lbl(self):
        lbl = Gtk.Label(label="")
        lbl.set_halign(Gtk.Align.START)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        return lbl

    def _make_switch(self, label_text, key, parent):
        box = Gtk.Box(spacing=6)
        lbl = Gtk.Label(label=label_text)
        sw = Gtk.Switch()
        sw.set_active(settings.get(key))
        sw.connect("notify::active", lambda s, _: settings.set_value(key, s.get_active()))
        box.pack_start(lbl, False, False, 0)
        box.pack_start(sw, False, False, 0)
        parent.pack_start(box, False, False, 0)
        return sw

    def _ts(self):
        return datetime.now().strftime("%H:%M:%S")

    def _log(self, text):
        end = self.output_buf.get_end_iter()
        self.output_buf.insert(end, f"[{self._ts()}] {text}\n")
        self.output_view.scroll_to_iter(self.output_buf.get_end_iter(), 0, False, 0, 0)

    def _set_result(self, lbl, ok, msg):
        short = msg[:90] + "…" if len(msg) > 90 else msg
        lbl.set_text(("✅ " if ok else "❌ ") + short)
        lbl.get_style_context().remove_class("result-ok")
        lbl.get_style_context().remove_class("result-fail")
        lbl.get_style_context().add_class("result-ok" if ok else "result-fail")

    def _load_history(self, path):
        ok, out = git_ops.run_custom(path, "git log --oneline -8")
        self.history_buf.set_text(out if ok else "(no commits yet)")

    def _load_diff(self):
        if not self.project_path: return
        self.diff_buf.set_text("")
        _, stat = git_ops.run_custom(self.project_path, "git diff --stat HEAD")
        _, diff = git_ops.run_custom(self.project_path, "git diff HEAD")
        for line in ((stat or "") + "\n" + (diff or "")).splitlines():
            end = self.diff_buf.get_end_iter()
            if line.startswith("+") and not line.startswith("+++"):
                self.diff_buf.insert_with_tags_by_name(end, line + "\n", "add")
            elif line.startswith("-") and not line.startswith("---"):
                self.diff_buf.insert_with_tags_by_name(end, line + "\n", "remove")
            elif line.startswith("@@") or line.startswith("diff "):
                self.diff_buf.insert_with_tags_by_name(end, line + "\n", "header")
            else:
                self.diff_buf.insert(end, line + "\n")

    def _toggle_history(self, btn):
        self.history_revealer.set_reveal_child(btn.get_active())

    def _toggle_diff(self, btn):
        self.diff_revealer.set_reveal_child(btn.get_active())
        if btn.get_active():
            self._load_diff()

    def _on_key_press(self, widget, event):
        ctrl = event.state & Gdk.ModifierType.CONTROL_MASK
        if ctrl and event.keyval == Gdk.KEY_Return:
            self._do_quick_commit(None)

    def _on_branch_change(self):
        if self.project_path:
            branch = git_ops.get_current_branch(self.project_path)
            status = git_ops.get_status(self.project_path)
            changed = len(status.splitlines()) if status else 0
            self.status_label.set_text(f"⎇  {branch}   |   {changed} changed file(s)")

    def _known_commit_prefixes(self):
        prefixes = [prefix for _name, prefix in COMMIT_TEMPLATES]

        custom = settings.get("custom_commit_templates") or []
        for item in custom:
            prefix = item.get("prefix", "").strip()
            if prefix:
                if not prefix.endswith(" "):
                    prefix += " "
                prefixes.append(prefix)

        return prefixes

    def _set_commit_validator_state(self, css_class, text):
        ctx = self.commit_validator_lbl.get_style_context()
        for cls in ["commit-validator-neutral", "commit-validator-good", "commit-validator-warn", "commit-validator-bad"]:
            ctx.remove_class(cls)
        ctx.add_class(css_class)
        self.commit_validator_lbl.set_text(text)

    def _validate_commit_message(self, _entry=None):
        msg = self.commit_entry.get_text().strip()
        if not hasattr(self, "commit_validator_lbl"):
            return

        if not msg:
            self._set_commit_validator_state("commit-validator-bad", "❌ Commit message is empty")
            return

        prefixes = self._known_commit_prefixes()
        if any(msg.startswith(prefix) for prefix in prefixes):
            if len(msg.split(":", 1)[-1].strip()) < 4:
                self._set_commit_validator_state("commit-validator-warn", "⚠ Prefix is good, but description is very short")
            else:
                self._set_commit_validator_state("commit-validator-good", f"✅ Good commit: {msg[:70]}")
            return

        if ":" in msg.split()[0] if msg.split() else False:
            self._set_commit_validator_state("commit-validator-warn", "⚠ Unknown commit type. Use ℹ Types or add it as custom.")
            return

        self._set_commit_validator_state("commit-validator-warn", "⚠ Consider using feat:, fix:, docs:, refactor:, test:, chore:, etc.")

    def _apply_template(self, _, prefix):
        current = self.commit_entry.get_text()
        # If already has a prefix, replace it; otherwise prepend
        if ": " in current:
            _, rest = current.split(": ", 1)
            self.commit_entry.set_text(prefix + rest)
        else:
            self.commit_entry.set_text(prefix + current)
        self.commit_entry.grab_focus()
        self.commit_entry.set_position(-1)

    def _on_notes_changed(self, buf):
        """Auto-save notes with a short debounce."""
        if not self.project_path:
            return
        from gi.repository import GLib
        if self._note_save_timeout:
            GLib.source_remove(self._note_save_timeout)
        def _save():
            s, e = buf.get_bounds()
            save_note(self.project_path, buf.get_text(s, e, False))
            self._note_save_timeout = None
            return False
        self._note_save_timeout = GLib.timeout_add(800, _save)

    # ── Public ───────────────────────────────────────────────────────────────

    def set_project(self, path):
        self.project_path = path
        self.project_label.set_markup(f"<b>{os.path.basename(path)}</b>")
        self.quick_btn.set_sensitive(True)

        branch = git_ops.get_current_branch(path)
        status = git_ops.get_status(path)
        changed = len(status.splitlines()) if status else 0
        self.status_label.set_text(f"⎇  {branch}   |   {changed} changed file(s)")

        remotes = git_ops.get_remotes(path)
        self.remote_combo.remove_all()
        for r in (remotes or ["origin"]):
            self.remote_combo.append_text(r)
        self.remote_combo.set_active(0)

        self._load_history(path)
        self.branch_panel.refresh(path)
        self.stash_panel_widget.refresh(path)
        self.pull_panel.refresh(path)
        self.tag_panel_widget.refresh(path)
        project_manager.add_recent(path)
        self._log(f"─── {os.path.basename(path)} ───")

        # Load notes
        note = get_note(path)
        self.notes_buf.handler_block_by_func(self._on_notes_changed)
        self.notes_buf.set_text(note)
        self.notes_buf.handler_unblock_by_func(self._on_notes_changed)

        if settings.get("auto_git_add"):
            self._do_add(None)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _do_add(self, _):
        if not self.project_path: return
        target = self.add_entry.get_text().strip() or "."
        ok, out = git_ops.git_add(self.project_path, target)
        self._set_result(self.add_result, ok, out or "Staged successfully")
        self._log(f"git add {target} → {'ok' if ok else out}")

    def _do_commit(self, _):
        if not self.project_path: return
        msg = self.commit_entry.get_text().strip()
        if not msg:
            self._set_result(self.commit_result, False, "Commit message is empty!")
            return
        ok, out = git_ops.git_commit(self.project_path, msg)
        activity.log_event(
            self.project_path,
            "commit_success" if ok else "commit_failed",
            msg if ok else f"Commit failed: {out[:120]}",
        )
        self._set_result(self.commit_result, ok, out)
        self._log(f"git commit \"{msg}\" → {'ok' if ok else out}")
        if ok:
            self.commit_entry.set_text("")
            self._load_history(self.project_path)
            notify.committed(msg, os.path.basename(self.project_path))
            if settings.get("auto_git_push"):
                self._do_push(None)

    def _do_push(self, _):
        if not self.project_path: return
        remote = self.remote_combo.get_active_text() or "origin"
        ok, out = git_ops.git_push(self.project_path, remote)
        activity.log_event(
            self.project_path,
            "push_success" if ok else "push_failed",
            f"{remote}: {out[:120] if out else 'pushed'}",
        )
        self._set_result(self.push_result, ok, out)
        self._log(f"git push {remote} → {'ok' if ok else out}")
        proj = os.path.basename(self.project_path)
        if ok:
            notify.pushed(remote, proj)
        else:
            notify.push_failed(remote, proj, out)

    def _do_push_all(self, _):
        if not self.project_path: return
        remotes = git_ops.get_remotes(self.project_path)
        all_ok = True
        for r in remotes:
            ok, out = git_ops.git_push(self.project_path, r)
            activity.log_event(
                self.project_path,
                "push_success" if ok else "push_failed",
                f"{r}: {out[:120] if out else 'pushed'}",
            )
            self._log(f"git push {r} → {'ok' if ok else out}")
            if not ok:
                all_ok = False
                notify.push_failed(r, os.path.basename(self.project_path), out)
            else:
                notify.pushed(r, os.path.basename(self.project_path))
        self._set_result(self.push_result, all_ok,
                        f"Pushed to {len(remotes)} remote(s)" if all_ok else "Some pushes failed")

    def _do_push_auth_terminal(self, _):
        if not self.project_path: return
        remote = self.remote_combo.get_active_text() or "origin"
        cmd = f"cd '{self.project_path}' && git push {remote}; echo; echo '--- Press Enter to close ---'; read"
        term = settings.get("terminal_cmd")
        for t in [term, "kitty", "x-terminal-emulator", "gnome-terminal", "xterm"]:
            try:
                if t == "kitty":
                    subprocess.Popen(["kitty", "--hold", "bash", "-c", cmd])
                else:
                    subprocess.Popen([t, "--", "bash", "-c", cmd])
                self._log(f"🔐 Terminal for git push {remote}")
                return
            except FileNotFoundError:
                continue

    def _do_custom(self, _):
        if not self.project_path: return
        cmd = self.custom_entry.get_text().strip()
        if not cmd: return
        ok, out = git_ops.run_custom(self.project_path, cmd)
        self._set_result(self.custom_result, ok, out)
        self._log(f"$ {cmd} → {out[:60]}")

    def _do_quick_commit(self, _):
        if not self.project_path: return
        msg = self.commit_entry.get_text().strip()
        if not msg:
            self._set_result(self.commit_result, False, "Need a commit message!")
            self.commit_entry.grab_focus()
            return
        self._log("⚡ Quick commit…")
        self._do_add(None)
        self._do_commit(None)
        self._do_push_all(None)
        self._log("⚡ Done!")


# ── Multi-Commit safety/validator patch ─────────────────────────────────────
# Non-invasive wrappers: normal commit flow remains unchanged.
try:
    from gi.repository import Gtk
    from core import command_safety
except Exception:
    Gtk = None
    command_safety = None


def _mc_commit_feedback(message):
    msg = (message or "").strip()

    if not msg:
        return ("dialog-error-symbolic", "Commit message is empty.")

    if len(msg) > 72:
        return ("dialog-warning-symbolic", "Commit message is over 72 characters. Still allowed, just less tidy.")

    prefixes = ("feat:", "fix:", "docs:", "refactor:", "test:", "chore:", "style:", "perf:", "ci:", "build:")
    if msg.startswith(prefixes):
        return ("emblem-ok-symbolic", "Good conventional-style commit message.")

    if ":" not in msg:
        return ("dialog-warning-symbolic", "Tip: consider a prefix like feat:, fix:, docs:, refactor:, test:, chore:.")

    return ("emblem-ok-symbolic", "Looks fine.")


def _mc_validate_commit_entry(self, *_):
    if Gtk is None or not hasattr(self, "commit_entry"):
        return

    icon, tip = _mc_commit_feedback(self.commit_entry.get_text())

    try:
        self.commit_entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY, icon)
        self.commit_entry.set_icon_tooltip_text(Gtk.EntryIconPosition.SECONDARY, tip)
        self.commit_entry.set_tooltip_text(tip)
    except Exception:
        pass


def _mc_confirm_risky_command(self, command):
    if Gtk is None or command_safety is None:
        return True

    if not command_safety.is_dangerous(command):
        return True

    dlg = Gtk.MessageDialog(
        transient_for=self.get_toplevel(),
        flags=0,
        message_type=Gtk.MessageType.WARNING,
        buttons=Gtk.ButtonsType.YES_NO,
        text="Risky command detected"
    )
    dlg.format_secondary_text(command_safety.warning_text(command))
    response = dlg.run()
    dlg.destroy()

    return response == Gtk.ResponseType.YES


if not getattr(CommitPanel, "_mc_safety_validator_patch_applied", False):
    CommitPanel._mc_base_init = CommitPanel.__init__
    CommitPanel._mc_base_do_custom = getattr(CommitPanel, "_do_custom", None)

    def _mc_init(self, *args, **kwargs):
        CommitPanel._mc_base_init(self, *args, **kwargs)

        if hasattr(self, "commit_entry"):
            try:
                self.commit_entry.set_placeholder_text("feat: add useful thing")
                self.commit_entry.connect("changed", self._mc_validate_commit_entry)
                self._mc_validate_commit_entry()
            except Exception:
                pass

        if hasattr(self, "custom_entry"):
            try:
                self.custom_entry.set_tooltip_text(
                    "Custom commands are allowed. Multi-Commit warns before risky commands like reset --hard, clean -fd, rm -rf, push --force."
                )
            except Exception:
                pass

    def _mc_do_custom(self, *args, **kwargs):
        cmd = ""

        try:
            cmd = self.custom_entry.get_text().strip()
        except Exception:
            cmd = ""

        if cmd and not self._mc_confirm_risky_command(cmd):
            try:
                self._set_result(self.custom_result, False, "Risky command cancelled.")
            except Exception:
                pass
            return

        if CommitPanel._mc_base_do_custom:
            return CommitPanel._mc_base_do_custom(self, *args, **kwargs)

    CommitPanel.__init__ = _mc_init
    CommitPanel._do_custom = _mc_do_custom
    CommitPanel._mc_validate_commit_entry = _mc_validate_commit_entry
    CommitPanel._mc_confirm_risky_command = _mc_confirm_risky_command
    CommitPanel._mc_safety_validator_patch_applied = True

