"""Verify the engine, session lifecycle and TypeScript production build."""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    python = ROOT / (".venv/Scripts/python.exe" if sys.platform == "win32" else ".venv/bin/python")
    for command in (
        [str(python), "-m", "ruff", "check", "backend", "scripts", "tests"],
        [str(python), "-m", "pytest", "-q"],
        ["npm", "--prefix", "frontend", "run", "build"],
    ):
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
