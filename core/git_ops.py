"""Git operations — all subprocess calls live here."""
import subprocess

def _run(cmd, cwd):
    """Run a shell command in the given directory. Returns (success, output)."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd, shell=True,
            capture_output=True, text=True
        )
        output = result.stdout.strip() or result.stderr.strip()
        return result.returncode == 0, output
    except Exception as e:
        return False, str(e)

def git_add(path, target="."):
    return _run(f"git add {target}", path)

def git_commit(path, message):
    safe = message.replace('"', '\\"')
    return _run(f'git commit -m "{safe}"', path)

def git_push(path, remote="origin", branch=""):
    cmd = f"git push {remote} {branch}".strip()
    return _run(cmd, path)

def run_custom(path, command):
    return _run(command, path)

def get_remotes(path):
    """Return list of configured git remotes."""
    ok, out = _run("git remote", path)
    if ok and out:
        return out.splitlines()
    return []

def get_current_branch(path):
    ok, out = _run("git branch --show-current", path)
    return out if ok else "main"

def is_git_repo(path):
    ok, _ = _run("git rev-parse --is-inside-work-tree", path)
    return ok

def get_status(path):
    ok, out = _run("git status --short", path)
    return out if ok else ""

# ── Repo health helpers ─────────────────────────────────────────────────────

def get_ahead_behind(path):
    """Return (ahead, behind) compared with upstream, safely."""
    ok, out = _run("git rev-list --left-right --count @{u}...HEAD 2>/dev/null", path)
    if not ok or not out:
        return 0, 0
    try:
        behind, ahead = [int(x) for x in out.split()[:2]]
        return ahead, behind
    except Exception:
        return 0, 0


def get_latest_commit_subject(path):
    ok, out = _run("git log -1 --pretty=%s", path)
    return out if ok and out else "No commits"


def get_untracked_count(path):
    status = get_status(path)
    return sum(1 for line in status.splitlines() if line.startswith("??")) if status else 0


def get_stash_count(path):
    ok, out = _run("git stash list", path)
    return len(out.splitlines()) if ok and out else 0


def get_tag_count(path):
    ok, out = _run("git tag", path)
    return len(out.splitlines()) if ok and out else 0


def get_repo_health(path):
    status = get_status(path)
    ahead, behind = get_ahead_behind(path)
    return {
        "branch": get_current_branch(path),
        "changed": len(status.splitlines()) if status else 0,
        "untracked": get_untracked_count(path),
        "ahead": ahead,
        "behind": behind,
        "latest_commit": get_latest_commit_subject(path),
        "remotes": get_remotes(path),
        "stashes": get_stash_count(path),
        "tags": get_tag_count(path),
    }
