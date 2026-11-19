"""Install locked dependencies and download the verified model once."""
import hashlib
import shutil
import subprocess
import sys
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = (
    "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
    "hand_landmarker/float16/1/hand_landmarker.task"
)
SHA = "fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1"
SIZE = 7_819_105


def verified(data):
    return len(data) == SIZE and hashlib.sha256(data).hexdigest() == SHA


def main():
    if shutil.which("uv"):
        subprocess.run(["uv", "sync", "--locked"], cwd=ROOT, check=True)
    elif (3, 11) <= sys.version_info[:2] < (3, 13):
        subprocess.run([sys.executable, "-m", "venv", ".venv"], cwd=ROOT, check=True)
        python = ".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python"
        spec = tomllib.loads((ROOT / "pyproject.toml").read_text())
        dependencies = spec["project"]["dependencies"] + spec["dependency-groups"]["dev"]
        subprocess.run([python, "-m", "pip", "install", *dependencies], cwd=ROOT, check=True)
    else:
        raise SystemExit("Install uv or run this script with Python 3.11 or 3.12.")
    model = ROOT / ".cache/models/hand_landmarker.task"
    if not model.is_file() or not verified(model.read_bytes()):
        with urllib.request.urlopen(URL, timeout=45) as response:
            data = response.read(SIZE + 1)
        if not verified(data):
            raise SystemExit("MediaPipe model failed SHA-256 or size verification.")
        model.parent.mkdir(parents=True, exist_ok=True)
        tmp = model.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(model)
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("Install Node.js and npm to build the Studio.")
    subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=ROOT / "frontend", check=True)
    subprocess.run([npm, "run", "build"], cwd=ROOT / "frontend", check=True)


if __name__ == "__main__":
    main()
