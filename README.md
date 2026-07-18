# DevWise

> A Linux desktop project cockpit for Git, checklists, project sessions, code reviews, diagnostics and local developer workflows.

![Platform](https://img.shields.io/badge/platform-Linux-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![GTK](https://img.shields.io/badge/GTK-3.0-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-active-brightgreen)

---

## What is DevWise?

DevWise is a lightweight GTK3 desktop app for Linux that helps manage coding projects, Git workflows, project checklists, local issues, sessions, code reviews and handoffs from one cockpit.

Built on **Linux Mint Cinnamon** — works on any GTK3-compatible distro.

---

## Features

### Core Workflow
- **Step-by-step commit flow** — `git add` → `git commit` → `git push`, each with Enter key support
- **⚡ Quick Commit** (`Ctrl+Enter`) — stages, commits and pushes all remotes in one keystroke
- **Push All Remotes** — one click to push to every configured remote simultaneously
- **🔐 Push with Auth** — opens a terminal for password-protected remotes (e.g. university GitHub) safely

### Project Management
- **Recent projects list** — most recently used at the top, persisted across sessions
- **Per-project actions** — open in 📁 file manager, 💻 VSCode, or 🖥 terminal from the sidebar
- **🟢🟡🔴 Git status indicators** — see clean/unstaged/conflict state at a glance
- **Branch + remote badges** on each project row

### Git Tools (built-in)
- **🔍 Diff viewer** — colour-coded `git diff HEAD` with green additions and red removals
- **📜 Commit history** — collapsible log of last 8 commits
- **⎇ Branch manager** — create, switch and delete branches without leaving the app
- **📦 Stash manager** — save, apply, pop and drop stashes with optional descriptions
- **Custom command runner** — run any git command and see output inline

### Favourites
- **⭐ Favourite Commands** — save any shell command (not just git!) with a name and category
- **Quick-run from menubar** — run any favourite directly from the menu without opening the manager
- **Terminal mode** — favourites that need a password or interactive input open in your terminal automatically
- **Category filtering** — organise favourites by category (Git, System, Dev, etc.)

### Settings
- Auto `git add` on project select
- Auto `git push` after commit
- Configurable VSCode command, terminal emulator, default remote
- **Remotes / Accounts tab** — add/update git remotes per project, enable credential caching with custom timeout

---

## Screenshots

> _Coming soon — contributions welcome!_

---

## Installation

### Requirements

- Linux (GTK3-compatible distro)
- Python 3.10+
- git

### Quick Install

```bash
git clone https://github.com/Pixsl-Labs/DevWise.git
cd DevWise
chmod +x install.sh
./install.sh
```

The installer will:
- Install Python GTK3 dependencies via apt
- Create a `.desktop` file for your app menu and panel
- Register the app with your desktop environment

### Launch

```bash
# Terminal
python3 ~/Projects/DevWise/main.py

# Or via Ulauncher (Ctrl+Space) → type "DevWise"

# Or from your app menu / taskbar after install
```

---

## Adding to the Cinnamon Panel

See [PANEL_SETUP.md](PANEL_SETUP.md) for step-by-step instructions.

**Quickest method:**
1. Click the Menu button → find DevWise
2. Right-click → Add to panel

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Enter` | Quick Commit (add → commit → push all) |
| `Enter` | Confirm current step |
| `Ctrl+Q` | Quit |

---

## Project Structure

```
DevWise/
├── main.py                  # Entry point
├── install.sh               # Installer
├── PANEL_SETUP.md           # Panel/taskbar setup guide
│
├── core/
│   ├── git_ops.py           # All git subprocess calls
│   ├── project_manager.py   # Recent projects persistence
│   ├── settings.py          # User settings (JSON)
│   └── favourites.py        # Favourite commands persistence
│
├── ui/
│   ├── main_window.py       # Main GTK window + menubar
│   ├── project_list.py      # Left panel — project list
│   ├── commit_panel.py      # Right panel — commit flow
│   ├── branch_panel.py      # Branch manager widget
│   ├── stash_panel.py       # Stash manager widget
│   ├── favourites_dialog.py # Favourites manager
│   └── settings_dialog.py   # Settings + remotes dialog
│
└── assets/
    └── icon.png             # App icon (git logo)
```

---

## Configuration

Settings are stored in `~/.config/devwise/`:

| File | Contents |
|------|----------|
| `settings.json` | App preferences |
| `recent.json` | Recent project paths |
| `favourites.json` | Saved favourite commands |

---

## Use Case: Multiple GitHub Accounts

DevWise was built to solve the problem of pushing to both a **personal GitHub** and a **university/work GitHub** from the same repo:

```bash
# Add your remotes (or use the Remotes tab in Settings)
git remote add origin  https://github.com/personal-user/repo.git
git remote add uni     https://github.com/uni-user/repo.git

# Then "Push All Remotes" sends to both at once
# "Push with Auth" handles password-protected remotes safely
```

---

## Roadmap

- [ ] System tray / notification on push success
- [ ] Cinnamon applet wrapper
- [ ] `git pull` / fetch panel
- [ ] Dark/light theme toggle
- [ ] Tag manager
- [ ] GPG commit signing support

---

## Contributing

Pull requests welcome! Please open an issue first for major changes.

```bash
git clone https://github.com/Pixsl-Labs/DevWise.git
cd DevWise
python3 main.py  # run from source, no build step needed
```

---

## License

MIT — see [LICENSE](LICENSE) for details.

---

## Credits

- Git icon by [pocike on Flaticon](https://www.flaticon.com/free-icons/git)
- Built with Python + GTK3 on Linux Mint Cinnamon
- Made by [Pixsl-Labs](https://github.com/Pixsl-Labs)