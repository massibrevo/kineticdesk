"""Build the standalone macOS application after running the standard bootstrap."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = (
    "pyinstaller==6.22.3", "pyobjc-framework-WebKit==13.0",
    "pyobjc-framework-ApplicationServices==13.0",
)


def main():
    if sys.platform != "darwin":
        raise SystemExit("The desktop package must be built on macOS.")
    python = ROOT / ".venv/bin/python"
    if not python.is_file() or not (ROOT / ".cache/models/hand_landmarker.task").is_file():
        raise SystemExit("Run scripts/bootstrap.py first.")
    if uv := shutil.which("uv"):
        install = [uv, "pip", "install", "--python", str(python)]
    else:
        install = [str(python), "-m", "pip", "install"]
    subprocess.run([*install, *PACKAGES], cwd=ROOT, check=True)
    env = os.environ | {
        "PYINSTALLER_CONFIG_DIR": str(ROOT / ".cache/macos/pyinstaller"),
        "MPLCONFIGDIR": str(ROOT / ".cache/matplotlib"),
    }
    subprocess.run(["npm", "--prefix", "frontend", "run", "build"], cwd=ROOT, check=True)
    subprocess.run(
        [str(python), "-m", "PyInstaller", "--noconfirm", "--distpath", ".cache/macos/dist",
         "--workpath", ".cache/macos/build", "macos/KineticDesk.spec"],
        cwd=ROOT, env=env, check=True,
    )
    print(ROOT / ".cache/macos/dist/KineticDesk.app")


if __name__ == "__main__":
    main()
