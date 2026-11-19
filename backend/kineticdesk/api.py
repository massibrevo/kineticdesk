"""Single-origin UI and authenticated local command/telemetry channel."""
import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .assets import STUDIO
from .runtime import Runtime

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self' ws://127.0.0.1:*; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'none'; object-src 'none'"
)


def create_app(port=5174, runtime=None):
    runtime = runtime or Runtime()
    token = secrets.token_urlsafe(32)
    host = f"127.0.0.1:{port}"
    origin = f"http://{host}"

    # Keep the input watchdog independent of both the Studio UI and asyncio.
    @asynccontextmanager
    async def lifespan(_app):
        from threading import Event, Thread

        done = Event()

        def watch():
            while not done.wait(1 / 60):
                runtime.watchdog()

        worker = Thread(target=watch, name="input-watchdog", daemon=True)
        worker.start()
        try:
            yield
        finally:
            done.set()
            runtime.stop("shutdown")
            worker.join(timeout=.5)

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if request.headers.get("host") != host:
            return JSONResponse({"error": "invalid-host"}, status_code=403)
        if request.headers.get("origin") not in (None, origin):
            return JSONResponse({"error": "invalid-origin"}, status_code=403)
        response = await call_next(request)
        response.headers.update({
            "Content-Security-Policy": CSP,
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Cache-Control": "no-store",
        })
        return response

    @app.get("/api/health")
    def health():
        return runtime.health()

    @app.get("/api/session")
    def session(request: Request):
        if request.headers.get("sec-fetch-site") not in (None, "same-origin"):
            return JSONResponse({"error": "invalid-site"}, status_code=403)
        return {"token": token}

    async def send_snapshots(ws, owner):
        last_preview = object()
        while True:
            snapshot = await asyncio.to_thread(runtime.snapshot_for, owner)
            if snapshot is None:
                await ws.close(code=1011, reason="lease-expired")
                return
            preview = snapshot["preview"]
            if preview == last_preview:
                del snapshot["preview"]
            else:
                last_preview = preview
            await ws.send_json(snapshot)
            await asyncio.sleep(1 / 30)

    async def receive_commands(ws, owner):
        while True:
            raw = await ws.receive_text()
            if len(raw) > 4096:
                await ws.close(code=1009)
                return
            message = json.loads(raw)
            if not isinstance(message, dict):
                await ws.close(code=1008)
                return
            await asyncio.to_thread(runtime.handle, owner, message)

    @app.websocket("/ws")
    async def socket(ws: WebSocket):
        if ws.headers.get("host") != host or ws.headers.get("origin") != origin:
            await ws.close(code=1008)
            return
        await ws.accept()
        owner = object()
        tasks = []
        try:
            login = await asyncio.wait_for(ws.receive_text(), timeout=3)
            if len(login) > 128 or not secrets.compare_digest(login.encode(), token.encode()):
                await ws.close(code=1008)
                return
            if not runtime.connect(owner):
                await ws.close(code=1008, reason="studio-in-use")
                return
            tasks = [
                asyncio.create_task(send_snapshots(ws, owner)),
                asyncio.create_task(receive_commands(ws, owner)),
            ]
            completed, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in completed:
                task.result()
        except (WebSocketDisconnect, asyncio.TimeoutError, ValueError, RuntimeError):
            pass
        finally:
            await asyncio.to_thread(runtime.disconnect, owner)
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    @app.get("/")
    def studio():
        return FileResponse(STUDIO / "index.html")

    app.mount("/assets", StaticFiles(directory=STUDIO / "assets", check_dir=False))

    return app


def app_from_env():
    return create_app(int(os.environ.get("KINETICDESK_PORT", "5174")))
