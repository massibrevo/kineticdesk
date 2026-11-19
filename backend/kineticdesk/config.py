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


LANGUAGES = ("en", "it")


def config_root():
    return Path(os.getenv("KINETICDESK_CONFIG_DIR", str(DEFAULT_ROOT)))


def profile_path():
    return config_root() / "profile.json"


def load_profile():
    try:
        return Profile.model_validate_json(profile_path().read_text())
    except (OSError, ValueError):
        return Profile()


def save_profile(profile):
    _save_text(profile_path(), profile.model_dump_json(indent=2) + "\n")


def load_language():
    try:
        value = (config_root() / "language").read_text().strip()
        if value in LANGUAGES:
            return value
    except OSError:
        pass
    return "en"


def save_language(language):
    _save_text(config_root() / "language", language + "\n")


def _save_text(path, value):
    path.parent.mkdir(mode=0o700, exist_ok=True, parents=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(value)
    tmp.replace(path)
