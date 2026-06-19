"""Self-update helper for Multi-Commit.

Uses git fetch + upstream comparison so updates only appear when the local
checked-out branch is behind its remote upstream.
"""
import os
import sys
import subprocess
from datetime import datetime, timedelta
from core import settings

APP_VERSION = "1.0.0"
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _run(args, cwd=REPO_ROOT):
    try:
        result = subprocess.run(
            args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (result.stdout or result.stderr or "").strip()
        return result.returncode == 0, output
    except Exception as e:
        return False, str(e)


def _current_branch():
    ok, out = _run(["git", "branch", "--show-current"])
    return out if ok and out else "main"


def _upstream_ref():
    ok, out = _run(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"])
    return out if ok and out else None


def should_skip_prompt():
    mode = settings.get("update_later_mode")
    until = settings.get("update_later_until")

    if mode == "ignore":
        return True

    if until:
        try:
            return datetime.now() < datetime.fromisoformat(until)
        except Exception:
            return False

    return False


def defer_update(mode):
    if mode == "3h":
        settings.set_value("update_later_mode", "3h")
        settings.set_value("update_later_until", (datetime.now() + timedelta(hours=3)).isoformat(timespec="seconds"))
    elif mode == "online":
        settings.set_value("update_later_mode", "online")
        settings.set_value("update_later_until", "")
    elif mode == "close":
        settings.set_value("update_later_mode", "close")
        settings.set_value("update_later_until", "")
    elif mode == "ignore":
        settings.set_value("update_later_mode", "ignore")
        settings.set_value("update_later_until", "")


def clear_defer():
    settings.set_value("update_later_mode", "")
    settings.set_value("update_later_until", "")


def check_for_update(force_preview=False):
    if force_preview:
        return {
            "available": True,
            "preview": True,
            "current": APP_VERSION,
            "latest": "preview",
            "branch": _current_branch(),
            "behind": 1,
            "message": "Preview update available",
        }

    if should_skip_prompt():
        return {"available": False, "message": "Update check deferred"}

    ok, _ = _run(["git", "rev-parse", "--is-inside-work-tree"])
    if not ok:
        return {"available": False, "message": "Not running from a git repository"}

    _run(["git", "fetch", "--quiet", "--all", "--prune"])

    upstream = _upstream_ref()
    if not upstream:
        return {"available": False, "message": "No upstream branch configured"}

    ok, out = _run(["git", "rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
    if not ok:
        return {"available": False, "message": out or "Could not compare with remote"}

    try:
        ahead, behind = [int(x) for x in out.split()]
    except Exception:
        ahead, behind = 0, 0

    return {
        "available": behind > 0,
        "current": APP_VERSION,
        "latest": upstream,
        "branch": _current_branch(),
        "ahead": ahead,
        "behind": behind,
        "message": f"{behind} update(s) available from {upstream}" if behind else "Already up to date",
    }


def apply_update(progress_cb=None):
    clear_defer()

    def progress(frac, msg):
        if progress_cb:
            progress_cb(frac, msg)

    progress(0.10, "Checking repository...")
    ok, out = _run(["git", "rev-parse", "--is-inside-work-tree"])
    if not ok:
        return False, out or "Not a git repository"

    progress(0.25, "Fetching latest changes...")
    ok, out = _run(["git", "fetch", "--all", "--prune"])
    if not ok:
        return False, out or "Fetch failed"

    progress(0.55, "Pulling update with rebase...")
    ok, out = _run(["git", "pull", "--rebase"])
    if not ok:
        return False, out or "Update failed"

    progress(0.90, "Update complete. Preparing restart...")
    return True, out or "Updated successfully"


def restart_app():
    main_path = os.path.join(REPO_ROOT, "main.py")
    os.execv(sys.executable, [sys.executable, main_path])