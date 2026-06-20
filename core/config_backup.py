"""Export and restore Multi-Commit config backups."""
import os
import zipfile
from datetime import datetime

CONFIG_DIR = os.path.expanduser("~/.config/multi-commit")

BACKUP_FILES = [
    "settings.json",
    "recent.json",
    "favourites.json",
    "checklists.json",
    "notes.json",
    "project_groups.json",
    "project_commands.json",
    "activity.json",
]


def export_backup(output_path=None):
    os.makedirs(CONFIG_DIR, exist_ok=True)

    if output_path is None:
        name = "multi-commit-backup-" + datetime.now().strftime("%Y-%m-%d-%H%M") + ".zip"
        output_path = os.path.join(os.path.expanduser("~/Projects"), name)

    output_path = os.path.abspath(os.path.expanduser(output_path))

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in BACKUP_FILES:
            path = os.path.join(CONFIG_DIR, filename)
            if os.path.exists(path):
                zf.write(path, arcname=filename)

    return output_path


def restore_backup(zip_path):
    zip_path = os.path.abspath(os.path.expanduser(zip_path))
    os.makedirs(CONFIG_DIR, exist_ok=True)

    restored = []

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            base = os.path.basename(member)

            if base not in BACKUP_FILES:
                continue

            target = os.path.join(CONFIG_DIR, base)
            with zf.open(member) as src, open(target, "wb") as dst:
                dst.write(src.read())

            restored.append(base)

    return restored