"""Paths for the source checkout and the installed macOS application."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = getattr(sys, "_MEIPASS", None)
STUDIO = Path(BUNDLE) / "studio" if BUNDLE else ROOT / "frontend/dist"
MODEL = (
    Path(BUNDLE) / "models/hand_landmarker.task"
    if BUNDLE else ROOT / ".cache/models/hand_landmarker.task"
)
