"""Command safety guardrails for Multi-Commit.

This module does not block normal commands. It only identifies commands that
can destroy local work, delete files, or rewrite remote history.
"""
import re
import shlex


DANGEROUS_PATTERNS = [
    ("git reset --hard", "Can permanently discard local tracked-file changes."),
    ("git clean -fd", "Can permanently delete untracked files/folders."),
    ("git clean -xfd", "Can permanently delete ignored/untracked build files too."),
    ("git push --force", "Can rewrite remote history."),
    ("git push -f", "Can rewrite remote history."),
    ("git branch -D", "Can force-delete a branch."),
    ("git stash drop", "Can delete a saved stash."),
    ("git stash clear", "Can delete all saved stashes."),
    ("rm -rf", "Can permanently delete files/folders."),
    ("sudo rm", "Can delete protected files/folders."),
    ("chmod -R 777", "Can weaken permissions across folders."),
    ("chown -R", "Can change ownership recursively."),
    ("mkfs", "Can format a disk/partition."),
    ("dd if=", "Can overwrite disks/files."),
    (":(){", "Fork bomb pattern."),
]


def _norm(command: str) -> str:
    return re.sub(r"\s+", " ", command or "").strip().lower()


def assess(command: str) -> dict:
    """Return safety info for a shell command."""
    normalized = _norm(command)
    matches = []

    for pattern, reason in DANGEROUS_PATTERNS:
        if pattern in normalized:
            matches.append({"pattern": pattern, "reason": reason})

    # Extra catch for rm commands split by options, e.g. rm -fr /tmp/foo
    try:
        parts = shlex.split(command or "")
        if parts and parts[0] == "rm" and any("r" in p and "f" in p for p in parts[1:] if p.startswith("-")):
            if not any(m["pattern"] == "rm -rf" for m in matches):
                matches.append({"pattern": "rm recursive force", "reason": "Can permanently delete files/folders."})
    except Exception:
        pass

    severity = "high" if matches else "normal"

    return {
        "dangerous": bool(matches),
        "severity": severity,
        "matches": matches,
        "command": command or "",
    }


def is_dangerous(command: str) -> bool:
    return assess(command).get("dangerous", False)


def warning_text(command: str) -> str:
    info = assess(command)

    if not info.get("dangerous"):
        return ""

    lines = [
        "This command looks risky:",
        "",
        command.strip(),
        "",
        "Why Multi-Commit is warning you:",
    ]

    for match in info.get("matches", []):
        lines.append(f"- {match['pattern']}: {match['reason']}")

    lines.extend([
        "",
        "Continue only if you are sure.",
    ])

    return "\n".join(lines)


def safety_guide() -> str:
    lines = [
        "Multi-Commit command safety guardrails",
        "",
        "Normal commands run as usual.",
        "These warnings only appear for commands that may delete work, rewrite history, or damage files.",
        "",
        "Watched patterns:",
    ]

    for pattern, reason in DANGEROUS_PATTERNS:
        lines.append(f"- {pattern}: {reason}")

    return "\n".join(lines)
