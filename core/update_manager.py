"""Self-update and release helpers for Multi-Commit.

Safe design:
- Checks remote upstream with git fetch.
- Only offers updates when local branch is behind upstream.
- Refuses to update if local uncommitted changes exist.
- Uses git pull --ff-only, so it will not create merge commits.
- Release builder creates annotated tags and optional push.
"""
import os
import json
import sys
import subprocess
from datetime import datetime, timedelta
from core import settings

APP_VERSION = "1.2.0"
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
    ok, out = _run([
        "git",
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
    ])
    return out if ok and out else None


def is_git_repo():
    ok, _ = _run(["git", "rev-parse", "--is-inside-work-tree"])
    return ok


def has_uncommitted_changes():
    ok, out = _run(["git", "status", "--short"])
    return bool(ok and out.strip())


def latest_local_tag():
    ok, out = _run(["git", "describe", "--tags", "--abbrev=0"])
    return out if ok and out else ""


def latest_remote_tag():
    _run(["git", "fetch", "--quiet", "--tags"])
    ok, out = _run(["git", "tag", "--sort=-v:refname"])
    if not ok or not out:
        return ""
    return out.splitlines()[0].strip()


def repo_summary():
    branch = _current_branch()
    upstream = _upstream_ref() or "No upstream"
    ok_status, status = _run(["git", "status", "--short"])
    ok_head, head = _run(["git", "log", "-1", "--pretty=%h %s"])
    ok_remote, remotes = _run(["git", "remote", "-v"])

    return {
        "version": APP_VERSION,
        "branch": branch,
        "upstream": upstream,
        "dirty": bool(ok_status and status.strip()),
        "status": status if ok_status else "",
        "latest_commit": head if ok_head else "No commits",
        "local_tag": latest_local_tag(),
        "remote_tag": latest_remote_tag(),
        "remotes": remotes if ok_remote else "",
    }


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
        settings.set_value(
            "update_later_until",
            (datetime.now() + timedelta(hours=3)).isoformat(timespec="seconds"),
        )
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
            "message": "Preview update available — this is only a UI test.",
        }

    if should_skip_prompt():
        return {"available": False, "message": "Update prompt deferred."}

    if not is_git_repo():
        return {"available": False, "message": "Not running from a Git repository."}

    _run(["git", "fetch", "--quiet", "--all", "--prune", "--tags"])

    upstream = _upstream_ref()
    if not upstream:
        return {
            "available": False,
            "message": "No upstream branch configured. Set upstream before using self-update.",
        }

    ok, out = _run(["git", "rev-list", "--left-right", "--count", f"HEAD...{upstream}"])
    if not ok:
        return {"available": False, "message": out or "Could not compare with upstream."}

    try:
        ahead, behind = [int(x) for x in out.split()[:2]]
    except Exception:
        ahead, behind = 0, 0

    if behind <= 0:
        return {
            "available": False,
            "current": APP_VERSION,
            "latest": latest_remote_tag() or APP_VERSION,
            "branch": _current_branch(),
            "behind": 0,
            "ahead": ahead,
            "message": "Multi-Commit is up to date.",
        }

    return {
        "available": True,
        "current": APP_VERSION,
        "latest": latest_remote_tag() or f"{behind} commit(s) behind",
        "branch": _current_branch(),
        "upstream": upstream,
        "behind": behind,
        "ahead": ahead,
        "dirty": has_uncommitted_changes(),
        "message": f"{behind} update commit(s) available from {upstream}.",
    }


def apply_update():
    """Apply update safely. Returns dict with ok/message/restart."""
    if not is_git_repo():
        return {"ok": False, "message": "Not running from a Git repository.", "restart": False}

    if has_uncommitted_changes():
        return {
            "ok": False,
            "message": "Local changes detected. Commit/stash your work before updating.",
            "restart": False,
        }

    _run(["git", "fetch", "--quiet", "--all", "--prune", "--tags"])

    upstream = _upstream_ref()
    if not upstream:
        return {"ok": False, "message": "No upstream branch configured.", "restart": False}

    ok, out = _run(["git", "pull", "--ff-only"])
    if not ok:
        return {
            "ok": False,
            "message": out or "Update failed. Git could not fast-forward.",
            "restart": False,
        }

    clear_defer()
    return {
        "ok": True,
        "message": out or "Updated successfully.",
        "restart": True,
    }


def restart_app():
    main_py = os.path.join(REPO_ROOT, "main.py")
    os.execv(sys.executable, [sys.executable, main_py])


def generate_release_notes(version):
    last_tag = latest_local_tag()
    if last_tag:
        ok, out = _run(["git", "log", f"{last_tag}..HEAD", "--pretty=- %s"])
    else:
        ok, out = _run(["git", "log", "-12", "--pretty=- %s"])

    notes = out if ok and out else "- Initial release notes"

    return (
        f"# Multi-Commit {version}\n\n"
        f"Generated: {datetime.now().isoformat(timespec='seconds')}\n\n"
        f"## Changes\n\n{notes}\n\n"
        f"## Test checklist\n\n"
        f"- App opens successfully\n"
        f"- Main sidebar works\n"
        f"- Checklist opens and restores last item\n"
        f"- Update Center opens\n"
        f"- py_compile passes\n"
    )


def create_release(version, notes, push=False):
    version = (version or "").strip()

    if not version:
        return {"ok": False, "message": "Version cannot be empty."}

    if not version.startswith("v"):
        version = "v" + version

    ok, existing = _run(["git", "tag", "--list", version])
    if ok and existing.strip() == version:
        return {"ok": False, "message": f"Tag {version} already exists."}

    if has_uncommitted_changes():
        return {
            "ok": False,
            "message": "Commit your changes before creating a release tag.",
        }

    ok, out = _run(["git", "tag", "-a", version, "-m", notes or f"Release {version}"])
    if not ok:
        return {"ok": False, "message": out or "Could not create tag."}

    if push:
        ok_push, out_push = _run(["git", "push", "origin", version])
        if not ok_push:
            return {
                "ok": False,
                "message": f"Created tag {version}, but push failed:\n{out_push}",
            }

    return {
        "ok": True,
        "version": version,
        "message": f"Release tag {version} created" + (" and pushed." if push else "."),
    }


# ── Multi-Commit realtime test update patch ─────────────────────────────────
#
# This creates a local fake update event for testing the update popup while the
# app is already open. It does NOT pull code or change Git history.

TEST_UPDATE_FILE = os.path.join(
    getattr(settings, "CONFIG_DIR", os.path.expanduser("~/.config/multi-commit")),
    "test_update_available.json"
)


def _test_update_now_id():
    return datetime.now().strftime("test-%Y%m%d-%H%M%S")


def create_test_update(message=None):
    os.makedirs(os.path.dirname(TEST_UPDATE_FILE), exist_ok=True)

    payload = {
        "id": _test_update_now_id(),
        "created": datetime.now().isoformat(timespec="seconds"),
        "current": APP_VERSION,
        "latest": "vTEST-LIVE",
        "behind": 1,
        "branch": _current_branch(),
        "message": message or "Live test update available — popup should appear while app is open.",
    }

    with open(TEST_UPDATE_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return test_update_info()


def clear_test_update():
    try:
        if os.path.exists(TEST_UPDATE_FILE):
            os.remove(TEST_UPDATE_FILE)
    except Exception:
        pass


def test_update_info():
    if not os.path.exists(TEST_UPDATE_FILE):
        return None

    try:
        with open(TEST_UPDATE_FILE, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return None

    return {
        "available": True,
        "test": True,
        "id": payload.get("id") or _test_update_now_id(),
        "current": payload.get("current", APP_VERSION),
        "latest": payload.get("latest", "vTEST-LIVE"),
        "branch": payload.get("branch", _current_branch()),
        "behind": int(payload.get("behind", 1)),
        "message": payload.get("message", "Live test update available."),
    }


_mc_original_check_for_update = check_for_update
_mc_original_apply_update = apply_update


def check_for_update(force_preview=False):
    if force_preview:
        return _mc_original_check_for_update(force_preview=True)

    test_info = test_update_info()
    if test_info:
        return test_info

    return _mc_original_check_for_update(force_preview=False)


def apply_update():
    test_info = test_update_info()

    if test_info:
        clear_test_update()
        return {
            "ok": True,
            "message": "Test update applied/cleared. Real updater was not run.",
            "restart": False,
            "test": True,
        }

    return _mc_original_apply_update()


# ── Multi-Commit performance update watcher patch ───────────────────────────
def live_update_info():
    """
    Lightweight live update check for the open app.

    IMPORTANT:
    This must never run git fetch / network commands.
    It only checks the local test-update file used for realtime popup testing.
    Manual Update Center checks still use the full remote updater.
    """
    tester = globals().get("test_update_info")

    if callable(tester):
        return tester()

    return None

