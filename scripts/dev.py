"""Run the Studio and API on one loopback origin."""
import argparse
import os
import pathlib
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def probe(port):
    url = f"http://127.0.0.1:{port}"
    for _ in range(35):
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=.6) as response:
                report = response.read().decode()
            with urllib.request.urlopen(url, timeout=.6) as response:
                if response.status != 200:
                    continue
            print(f"Studio {url}\n{report}", flush=True)
            return
        except OSError:
            time.sleep(.15)


def main():
    args = argparse.ArgumentParser()
    args.add_argument("--port", type=int, default=int(os.getenv("KINETICDESK_PORT", "5173")))
    config = args.parse_args()
    virtualenv = ROOT / (".venv/Scripts/python.exe" if sys.platform == "win32"
                         else ".venv/bin/python")
    if sys.prefix == sys.base_prefix and virtualenv.is_file():
        return subprocess.call([str(virtualenv), __file__, "--port", str(config.port)])
    if not (ROOT / "frontend/dist/index.html").exists():
        raise SystemExit("Run scripts/bootstrap.py to build the Studio first.")
    import uvicorn

    sys.path.insert(0, str(ROOT / "backend"))
    from kineticdesk.api import create_app

    # Probe after Uvicorn has bound the socket to avoid reporting another service's URL.
    class Server(uvicorn.Server):
        async def startup(self, sockets=None):
            await super().startup(sockets=sockets)
            if self.started:
                threading.Thread(target=probe, args=(config.port,), daemon=True).start()

    app = create_app(config.port)
    Server(uvicorn.Config(
        app, host="127.0.0.1", port=config.port, ws_max_size=4096,
        timeout_graceful_shutdown=2,
    )).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
