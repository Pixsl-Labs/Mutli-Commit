"""Diagnostics window for Multi-Commit."""
import os
import platform
import subprocess
import sys
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

from core import settings


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run(command, timeout=12):
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, output
    except Exception as e:
        return False, str(e)


class DiagnosticsWindow(Gtk.Window):
    def __init__(self, parent=None, project_path=None):
        super().__init__(title="🩺 Multi-Commit Diagnostics")
        self.parent_window = parent
        self.project_path = project_path
        self.set_default_size(780, 560)
        self.set_position(Gtk.WindowPosition.CENTER)
        self._build()
        self.refresh_report()
        self.show_all()

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_border_width(10)
        self.add(root)

        header = Gtk.Label()
        header.set_markup("<b>🩺 Diagnostics</b>")
        header.set_halign(Gtk.Align.START)
        root.pack_start(header, False, False, 0)

        btn_row = Gtk.Box(spacing=6)
        root.pack_start(btn_row, False, False, 0)

        refresh_btn = Gtk.Button(label="Refresh Report")
        refresh_btn.connect("clicked", lambda _: self.refresh_report())
        btn_row.pack_start(refresh_btn, False, False, 0)

        compile_btn = Gtk.Button(label="Run Compile Check")
        compile_btn.connect("clicked", lambda _: self.run_compile_check())
        btn_row.pack_start(compile_btn, False, False, 0)

        copy_btn = Gtk.Button(label="Copy Report")
        copy_btn.connect("clicked", lambda _: self.copy_report())
        btn_row.pack_start(copy_btn, False, False, 0)

        self.status_lbl = Gtk.Label(label="")
        self.status_lbl.set_halign(Gtk.Align.START)
        btn_row.pack_start(self.status_lbl, True, True, 0)

        scroll = Gtk.ScrolledWindow()
        self.view = Gtk.TextView()
        self.view.set_editable(False)
        self.view.set_monospace(True)
        self.buf = self.view.get_buffer()
        scroll.add(self.view)
        root.pack_start(scroll, True, True, 0)

    def _set_text(self, text):
        self.buf.set_text(text or "")

    def _get_text(self):
        start, end = self.buf.get_bounds()
        return self.buf.get_text(start, end, False)

    def refresh_report(self):
        ok_status, git_status = _run("git status --short")
        ok_branch, branch = _run("git branch --show-current")
        ok_commit, commit = _run("git log -1 --pretty='%h %s'")
        ok_remotes, remotes = _run("git remote -v")
        ok_files, files = _run("find core ui -maxdepth 1 -name '*.py' | sort | wc -l")

        config_dir = getattr(settings, "CONFIG_DIR", os.path.expanduser("~/.config/multi-commit"))

        lines = [
            "=== Multi-Commit Diagnostics ===",
            f"Python: {sys.version.split()[0]}",
            f"Platform: {platform.platform()}",
            f"Repo: {REPO_ROOT}",
            f"Selected project: {self.project_path or 'none'}",
            f"Config dir: {config_dir}",
            "",
            "=== Git ===",
            f"Branch: {branch if ok_branch else 'unknown'}",
            f"Latest commit: {commit if ok_commit else 'unknown'}",
            f"Changed files: {len(git_status.splitlines()) if ok_status and git_status else 0}",
            f"Python files found: {files if ok_files else 'unknown'}",
            "",
            "=== Remotes ===",
            remotes if ok_remotes and remotes else "No remotes found.",
            "",
            "=== Status ===",
            git_status if ok_status and git_status else "Clean working tree.",
            "",
            "Tip: run 'Compile Check' before giving me feedback or before pushing a big change.",
        ]

        self._set_text("\n".join(lines))
        self.status_lbl.set_text("Report refreshed.")

    def run_compile_check(self):
        self.status_lbl.set_text("Running compile check...")
        ok, out = _run("python3 -m py_compile main.py core/*.py ui/*.py", timeout=25)

        current = self._get_text()
        result = [
            current,
            "",
            "=== Compile Check ===",
            "PASS ✅" if ok else "FAIL ❌",
            out or "No output.",
        ]

        self._set_text("\n".join(result))
        self.status_lbl.set_text("Compile check passed." if ok else "Compile check failed.")

    def copy_report(self):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self._get_text(), -1)
        self.status_lbl.set_text("Report copied.")
