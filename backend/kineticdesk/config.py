"""Local calibration profile. Video and landmarks are never written."""
import os
import sys
from pathlib import Path

from .gestures import Profile

if sys.platform == "darwin":
    DEFAULT_ROOT = Path.home() / "Library/Application Support/KineticDesk"
elif sys.platform == "win32":
    DEFAULT_ROOT = Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "KineticDesk"
else:
    DEFAULT_ROOT = Path(os.getenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "kineticdesk"


def profile_path():
    return Path(os.getenv("KINETICDESK_CONFIG_DIR", str(DEFAULT_ROOT))) / "profile.json"


def load_profile():
    try:
        return Profile.model_validate_json(profile_path().read_text())
    except (OSError, ValueError):
        return Profile()


def save_profile(profile):
    path = profile_path()
    path.parent.mkdir(mode=0o700, exist_ok=True, parents=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(profile.model_dump_json(indent=2) + "\n")
    tmp.replace(path)
