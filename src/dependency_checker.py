import shutil
import sys

REQUIRED_DEPENDENCIES = [
    "wget",
    "unzip",
    "cabextract",
    "zenity",
    "xdg-open",
    "pkill",
    "update-desktop-database",
    "uv"
]

def check_dependencies():
    """
    Check if all required system dependencies are installed.
    Exits the program with an error message if any are missing.
    """
    missing_deps = []

    for dep in REQUIRED_DEPENDENCIES:
        if not shutil.which(dep):
            missing_deps.append(dep)

    return missing_deps
