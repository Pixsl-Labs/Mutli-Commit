"""Middle project dashboard — visible project context between sidebar and Git tools."""
import os
import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Pango, Gdk
from core import git_ops


class ProjectDashboard(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.project_path = None
        self.set_size_request(260, -1)
        self._apply_css()
        self._build()

    def _apply_css(self):
        css = b"""
        .dashboard-header {
            background: alpha(white, 0.04);
            border-bottom: 1px solid alpha(white, 0.1);
            padding: 10px;
        }
        .dashboard-card {
            background: alpha(white, 0.035);
            border: 1px solid alpha(white, 0.08);
            border-radius: 7px;
            padding: 8px;
            margin: 5px 8px;
        }
        .dashboard-title { font-size: 12px; font-weight: bold; }
        .dashboard-muted { font-size: 10px; opacity: 0.55; }
        .dashboard-value { font-size: 11px; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _build(self):
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        header.get_style_context().add_class("dashboard-header")
        self.title_lbl = Gtk.Label()
        self.title_lbl.set_markup("<b>Project Dashboard</b>")
        self.title_lbl.set_halign(Gtk.Align.START)
        header.pack_start(self.title_lbl, False, False, 0)
        self.path_lbl = Gtk.Label(label="Select a project to view dashboard")
        self.path_lbl.get_style_context().add_class("dashboard-muted")
        self.path_lbl.set_halign(Gtk.Align.START)
        self.path_lbl.set_ellipsize(Pango.EllipsizeMode.START)
        header.pack_start(self.path_lbl, False, False, 0)
        self.pack_start(header, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        scroll.add(self.inner)
        self.pack_start(scroll, True, True, 0)

        self.commands_box = self._card("⚡ Project Commands")
        self.commands_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.commands_box.pack_start(self.commands_content, False, False, 0)
        self.inner.pack_start(self.commands_box, False, False, 0)

        self.health_box = self._card("💚 Repo Health")
        self.health_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.health_box.pack_start(self.health_content, False, False, 0)
        self.inner.pack_start(self.health_box, False, False, 0)

        self.activity_box = self._card("🕘 Recent Activity")
        self.activity_content = Gtk.Label(label="Activity log coming soon.")
        self.activity_content.set_halign(Gtk.Align.START)
        self.activity_content.get_style_context().add_class("dashboard-muted")
        self.activity_box.pack_start(self.activity_content, False, False, 0)
        self.inner.pack_start(self.activity_box, False, False, 0)

        self.metrics_box = self._card("📊 Metrics")
        self.metrics_content = Gtk.Label(label="Local metrics coming soon.")
        self.metrics_content.set_halign(Gtk.Align.START)
        self.metrics_content.get_style_context().add_class("dashboard-muted")
        self.metrics_box.pack_start(self.metrics_content, False, False, 0)
        self.inner.pack_start(self.metrics_box, False, False, 0)

        self._refresh_empty()

    def _card(self, title):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.get_style_context().add_class("dashboard-card")
        lbl = Gtk.Label()
        lbl.set_markup(f"<b>{title}</b>")
        lbl.set_halign(Gtk.Align.START)
        lbl.get_style_context().add_class("dashboard-title")
        box.pack_start(lbl, False, False, 0)
        return box

    def _clear(self, box):
        for child in box.get_children():
            box.remove(child)

    def _row(self, label, value):
        row = Gtk.Box(spacing=6)
        left = Gtk.Label(label=label)
        left.set_halign(Gtk.Align.START)
        left.get_style_context().add_class("dashboard-muted")
        row.pack_start(left, True, True, 0)
        right = Gtk.Label(label=value)
        right.set_halign(Gtk.Align.END)
        right.set_ellipsize(Pango.EllipsizeMode.END)
        right.get_style_context().add_class("dashboard-value")
        row.pack_end(right, False, False, 0)
        return row

    def _refresh_empty(self):
        self._clear(self.commands_content)
        self.commands_content.pack_start(Gtk.Label(label="Select a project first."), False, False, 0)
        self._clear(self.health_content)
        self.health_content.pack_start(Gtk.Label(label="No project selected."), False, False, 0)
        self.show_all()

    def set_project(self, path):
        self.project_path = path
        self.title_lbl.set_markup(f"<b>{os.path.basename(path)}</b>")
        self.path_lbl.set_text(path)
        self.refresh()

    def refresh(self):
        if not self.project_path:
            self._refresh_empty()
            return

        self._clear(self.commands_content)
        self.commands_content.pack_start(Gtk.Label(label="Per-project commands arrive in Stage 3."), False, False, 0)

        self._clear(self.health_content)
        branch = git_ops.get_current_branch(self.project_path)
        status = git_ops.get_status(self.project_path)
        changed = len(status.splitlines()) if status else 0
        remotes = git_ops.get_remotes(self.project_path)
        ok_commit, latest_commit = git_ops.run_custom(self.project_path, "git log -1 --pretty=%s")
        ok_stash, stash_out = git_ops.run_custom(self.project_path, "git stash list")
        ok_tags, tags_out = git_ops.run_custom(self.project_path, "git tag")

        self.health_content.pack_start(self._row("Branch", branch or "main"), False, False, 0)
        self.health_content.pack_start(self._row("Changed files", str(changed)), False, False, 0)
        self.health_content.pack_start(self._row("Remotes", ", ".join(remotes) if remotes else "none"), False, False, 0)
        self.health_content.pack_start(self._row("Latest commit", latest_commit if ok_commit and latest_commit else "none"), False, False, 0)
        self.health_content.pack_start(self._row("Stashes", str(len(stash_out.splitlines())) if ok_stash and stash_out else "0"), False, False, 0)
        self.health_content.pack_start(self._row("Tags", str(len(tags_out.splitlines())) if ok_tags and tags_out else "0"), False, False, 0)
        self.show_all()