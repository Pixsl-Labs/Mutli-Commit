"""DevWise Git Learning Center.

A practical Git reference window for DevWise users.
No repo changes are made from this window; it is read/copy/open only.
"""
import subprocess
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango


LEARN_GIT_BRANCHING_URL = "https://learngitbranching.js.org/?locale=en_US"


COMMANDS = [
    {
        "category": "Start here",
        "name": "git status",
        "command": "git status --short",
        "safe": "Safe",
        "what": "Shows what changed in your repo.",
        "when": "Use before every commit so you know exactly what will be staged/committed.",
        "example": "git status --short",
        "notes": "Short status is easier to scan inside terminals and DevWise.",
    },
    {
        "category": "Start here",
        "name": "git log",
        "command": "git log --oneline --graph --decorate --all -12",
        "safe": "Safe",
        "what": "Shows recent commits and branch structure.",
        "when": "Use when you want to understand where your branch is compared with others.",
        "example": "git log --oneline --graph --decorate --all -12",
        "notes": "The graph view is the closest terminal equivalent to a visual Git tree.",
    },
    {
        "category": "Daily workflow",
        "name": "git add",
        "command": "git add .",
        "safe": "Usually safe",
        "what": "Stages files ready for commit.",
        "when": "Use after reviewing your changes and before git commit.",
        "example": "git add .",
        "notes": "Use `git add file.py` for safer targeted staging.",
    },
    {
        "category": "Daily workflow",
        "name": "git commit",
        "command": 'git commit -m "feat: useful message"',
        "safe": "Safe",
        "what": "Saves staged changes as a local commit.",
        "when": "Use when a small piece of work is complete and tested.",
        "example": 'git commit -m "fix: repair checklist parser"',
        "notes": "DevWise suggests prefixes like feat:, fix:, docs:, refactor:, test:, chore:.",
    },
    {
        "category": "Daily workflow",
        "name": "git push",
        "command": "git push origin main",
        "safe": "Usually safe",
        "what": "Uploads local commits to a remote repo.",
        "when": "Use after committing, once you are ready to publish your work.",
        "example": "git push origin main",
        "notes": "If SSH fails, switch the remote to HTTPS or fix your GitHub SSH key.",
    },
    {
        "category": "Branching",
        "name": "git branch",
        "command": "git branch",
        "safe": "Safe",
        "what": "Lists local branches.",
        "when": "Use when checking which branches exist locally.",
        "example": "git branch",
        "notes": "The current branch is marked with `*`.",
    },
    {
        "category": "Branching",
        "name": "create branch",
        "command": "git checkout -b feat/example-branch",
        "safe": "Safe",
        "what": "Creates a new branch and switches to it.",
        "when": "Use before starting a feature, fix, experiment, or checklist issue.",
        "example": "git checkout -b feat/git-learning-center",
        "notes": "This matches DevWise Branch → Issue workflow nicely.",
    },
    {
        "category": "Branching",
        "name": "switch branch",
        "command": "git checkout main",
        "safe": "Safe unless uncommitted changes conflict",
        "what": "Switches to another branch.",
        "when": "Use when moving between features or returning to main.",
        "example": "git checkout main",
        "notes": "Commit/stash first if you have unfinished work.",
    },
    {
        "category": "Merging",
        "name": "git merge",
        "command": "git merge feat/example-branch",
        "safe": "Usually safe",
        "what": "Combines another branch into your current branch.",
        "when": "Use when a feature branch is finished and should be brought into main.",
        "example": "git checkout main && git merge feat/git-learning-center",
        "notes": "Conflicts can happen. DevWise should later add a merge conflict helper.",
    },
    {
        "category": "Merging",
        "name": "git rebase",
        "command": "git rebase main",
        "safe": "Advanced",
        "what": "Replays your branch commits on top of another branch.",
        "when": "Use to clean up feature branch history before merging.",
        "example": "git checkout feat/example && git rebase main",
        "notes": "Avoid rebasing shared branches unless you know the team workflow.",
    },
    {
        "category": "Remote",
        "name": "git remote -v",
        "command": "git remote -v",
        "safe": "Safe",
        "what": "Shows remote repo URLs.",
        "when": "Use when push/pull is failing or after renaming a GitHub repo.",
        "example": "git remote -v",
        "notes": "Useful after renaming Multi-Commit to DevWise.",
    },
    {
        "category": "Remote",
        "name": "change remote URL",
        "command": "git remote set-url origin https://github.com/Pixsl-Labs/DevWise.git",
        "safe": "Safe if URL is correct",
        "what": "Updates where origin points.",
        "when": "Use after renaming a GitHub repo or switching SSH/HTTPS.",
        "example": "git remote set-url origin https://github.com/Pixsl-Labs/DevWise.git",
        "notes": "Run `git remote -v` afterwards to confirm.",
    },
    {
        "category": "Undo / fix mistakes",
        "name": "git restore",
        "command": "git restore file.py",
        "safe": "Can discard file changes",
        "what": "Restores a file back to the last committed version.",
        "when": "Use when you want to undo uncommitted edits to one file.",
        "example": "git restore ui/main_window.py",
        "notes": "This discards local edits in that file. Use carefully.",
    },
    {
        "category": "Undo / fix mistakes",
        "name": "git restore --staged",
        "command": "git restore --staged file.py",
        "safe": "Safe",
        "what": "Unstages a file without deleting the changes.",
        "when": "Use when you accidentally staged too much.",
        "example": "git restore --staged ui/main_window.py",
        "notes": "Your file changes remain in the working tree.",
    },
    {
        "category": "Undo / fix mistakes",
        "name": "git revert",
        "command": "git revert HEAD",
        "safe": "Safe for shared history",
        "what": "Creates a new commit that undoes a previous commit.",
        "when": "Use when a pushed commit needs to be undone safely.",
        "example": "git revert HEAD",
        "notes": "Better than reset for commits already pushed.",
    },
    {
        "category": "Stash",
        "name": "git stash",
        "command": 'git stash push -m "work in progress"',
        "safe": "Usually safe",
        "what": "Temporarily saves uncommitted work.",
        "when": "Use before switching branches or pulling when your work is unfinished.",
        "example": 'git stash push -m "before testing updater"',
        "notes": "Use `git stash list` to view saved stashes.",
    },
    {
        "category": "Stash",
        "name": "git stash pop",
        "command": "git stash pop",
        "safe": "Can create conflicts",
        "what": "Restores the latest stash and removes it from the stash list.",
        "when": "Use when returning to previously saved work.",
        "example": "git stash pop",
        "notes": "Use `git stash apply` if you want to keep the stash after applying.",
    },
    {
        "category": "Tags / releases",
        "name": "git tag",
        "command": 'git tag -a v1.2.0 -m "Release v1.2.0"',
        "safe": "Safe if version is correct",
        "what": "Creates a named release point.",
        "when": "Use for stable versions of DevWise or SentinelIR.",
        "example": 'git tag -a v1.2.0 -m "Release v1.2.0"',
        "notes": "Push with `git push origin v1.2.0`.",
    },
    {
        "category": "Danger zone",
        "name": "git reset --hard",
        "command": "git reset --hard HEAD",
        "safe": "Dangerous",
        "what": "Discards tracked local changes.",
        "when": "Only use when you deliberately want to throw away local edits.",
        "example": "git reset --hard HEAD",
        "notes": "DevWise warns before commands like this. Prefer backup/stash first.",
    },
    {
        "category": "Danger zone",
        "name": "git clean -fd",
        "command": "git clean -fd",
        "safe": "Dangerous",
        "what": "Deletes untracked files/folders.",
        "when": "Only use when you are sure untracked files are junk.",
        "example": "git clean -fd",
        "notes": "Run `git clean -fdn` first for a dry run.",
    },
    {
        "category": "Danger zone",
        "name": "git push --force",
        "command": "git push --force",
        "safe": "Dangerous",
        "what": "Overwrites remote history.",
        "when": "Avoid unless you intentionally rewrote history and understand the impact.",
        "example": "git push --force-with-lease",
        "notes": "Prefer `--force-with-lease` over `--force`, but still be careful.",
    },
]


class GitLearningWindow(Gtk.Window):
    def __init__(self, parent=None, project_path=None):
        super().__init__(title="📚 DevWise Git Learning Center")
        self.parent_window = parent
        self.project_path = project_path
        self.selected = None

        self.set_default_size(880, 620)
        self.set_position(Gtk.WindowPosition.CENTER)
        self._build()
        self._refresh_list()
        self.show_all()

    def _build(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        root.set_border_width(10)
        self.add(root)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)

        title = Gtk.Label()
        title.set_markup("<b>📚 Git Learning Center</b>")
        title.set_halign(Gtk.Align.START)
        header.pack_start(title, False, False, 0)

        desc = Gtk.Label(
            label=(
                "A practical Git command guide for DevWise. "
                "Nothing here changes your repo unless you copy a command and run it yourself."
            )
        )
        desc.set_halign(Gtk.Align.START)
        desc.set_line_wrap(True)
        header.pack_start(desc, False, False, 0)

        root.pack_start(header, False, False, 0)

        top_row = Gtk.Box(spacing=6)
        root.pack_start(top_row, False, False, 0)

        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text("Search commands, e.g. branch, push, undo, stash...")
        self.search.connect("search-changed", lambda *_: self._refresh_list())
        top_row.pack_start(self.search, True, True, 0)

        open_site = Gtk.Button(label="🌐 Open Learn Git Branching")
        open_site.set_tooltip_text("Open the interactive visual Git learning site in your browser")
        open_site.connect("clicked", lambda _: self._open_url(LEARN_GIT_BRANCHING_URL))
        top_row.pack_start(open_site, False, False, 0)

        copy_sheet = Gtk.Button(label="📋 Copy Cheat Sheet")
        copy_sheet.connect("clicked", lambda _: self._copy(self._cheat_sheet(), "Cheat sheet copied."))
        top_row.pack_start(copy_sheet, False, False, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(310)
        root.pack_start(paned, True, True, 0)

        left_scroll = Gtk.ScrolledWindow()
        self.command_list = Gtk.ListBox()
        self.command_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.command_list.connect("row-selected", self._on_selected)
        left_scroll.add(self.command_list)
        paned.pack1(left_scroll, resize=False, shrink=False)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        right.set_border_width(8)

        self.details_title = Gtk.Label()
        self.details_title.set_markup("<b>Select a command</b>")
        self.details_title.set_halign(Gtk.Align.START)
        right.pack_start(self.details_title, False, False, 0)

        details_scroll = Gtk.ScrolledWindow()
        self.details = Gtk.TextView()
        self.details.set_editable(False)
        self.details.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.details.set_monospace(True)
        self.details_buf = self.details.get_buffer()
        details_scroll.add(self.details)
        right.pack_start(details_scroll, True, True, 0)

        btn_row = Gtk.Box(spacing=6)
        right.pack_start(btn_row, False, False, 0)

        copy_cmd = Gtk.Button(label="📋 Copy Command")
        copy_cmd.connect("clicked", lambda _: self._copy_selected_command())
        btn_row.pack_start(copy_cmd, False, False, 0)

        copy_explain = Gtk.Button(label="📋 Copy Explanation")
        copy_explain.connect("clicked", lambda _: self._copy_selected_explanation())
        btn_row.pack_start(copy_explain, False, False, 0)

        self.status_lbl = Gtk.Label(label="Ready")
        self.status_lbl.set_halign(Gtk.Align.START)
        btn_row.pack_start(self.status_lbl, True, True, 0)

        paned.pack2(right, resize=True, shrink=False)

    def _matches(self, item, query):
        if not query:
            return True

        haystack = " ".join([
            item.get("category", ""),
            item.get("name", ""),
            item.get("command", ""),
            item.get("what", ""),
            item.get("when", ""),
            item.get("notes", ""),
        ]).lower()

        return query.lower() in haystack

    def _refresh_list(self):
        query = self.search.get_text().strip()

        for child in self.command_list.get_children():
            self.command_list.remove(child)

        current_category = None

        for item in COMMANDS:
            if not self._matches(item, query):
                continue

            if item["category"] != current_category:
                current_category = item["category"]
                header = Gtk.ListBoxRow()
                header.set_selectable(False)
                lbl = Gtk.Label(label=current_category)
                lbl.set_halign(Gtk.Align.START)
                lbl.set_margin_top(8)
                lbl.set_margin_bottom(3)
                lbl.set_margin_start(8)
                header.add(lbl)
                self.command_list.add(header)

            row = Gtk.ListBoxRow()
            row.payload = item

            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
            box.set_border_width(7)

            name = Gtk.Label(label=item["name"])
            name.set_halign(Gtk.Align.START)
            name.set_ellipsize(Pango.EllipsizeMode.END)
            box.pack_start(name, False, False, 0)

            cmd = Gtk.Label(label=item["command"])
            cmd.set_halign(Gtk.Align.START)
            cmd.set_ellipsize(Pango.EllipsizeMode.END)
            box.pack_start(cmd, False, False, 0)

            row.add(box)
            self.command_list.add(row)

        self.command_list.show_all()

    def _on_selected(self, _listbox, row):
        if row is None or not hasattr(row, "payload"):
            return

        self.selected = row.payload
        self.details_title.set_markup(f"<b>{self.selected['name']}</b>")
        self.details_buf.set_text(self._details_text(self.selected))

    def _details_text(self, item):
        return "\n".join([
            f"Command: {item.get('command', '')}",
            f"Category: {item.get('category', '')}",
            f"Safety: {item.get('safe', '')}",
            "",
            "What it does:",
            item.get("what", ""),
            "",
            "When to use it:",
            item.get("when", ""),
            "",
            "Example:",
            item.get("example", ""),
            "",
            "Notes:",
            item.get("notes", ""),
        ])

    def _copy_selected_command(self):
        if not self.selected:
            self.status_lbl.set_text("Select a command first.")
            return

        self._copy(self.selected.get("command", ""), "Command copied.")

    def _copy_selected_explanation(self):
        if not self.selected:
            self.status_lbl.set_text("Select a command first.")
            return

        self._copy(self._details_text(self.selected), "Explanation copied.")

    def _copy(self, text, message):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text or "", -1)
        self.status_lbl.set_text(message)

    def _open_url(self, url):
        try:
            subprocess.Popen(["xdg-open", url])
            self.status_lbl.set_text("Opened learning site.")
        except Exception as e:
            self.status_lbl.set_text(f"Could not open site: {e}")

    def _cheat_sheet(self):
        lines = ["# DevWise Git Cheat Sheet", ""]

        for item in COMMANDS:
            lines.extend([
                f"## {item['name']}",
                f"`{item['command']}`",
                "",
                f"- Category: {item['category']}",
                f"- Safety: {item['safe']}",
                f"- What: {item['what']}",
                f"- When: {item['when']}",
                f"- Notes: {item['notes']}",
                "",
            ])

        return "\n".join(lines).strip() + "\n"
