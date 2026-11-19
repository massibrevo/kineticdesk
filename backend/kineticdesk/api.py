"""Single-origin UI and authenticated local command/telemetry channel."""
import asyncio
import contextlib
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

    # Independent of asyncio, so a slow or disconnected browser cannot extend the input lease.
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
        return {"status": "ok", "device": runtime.device}

    @app.get("/api/session")
    def session(request: Request):
        if request.headers.get("sec-fetch-site") not in (None, "same-origin"):
            return JSONResponse({"error": "invalid-site"}, status_code=403)
        return {"token": token}

    async def send_snapshots(ws):
        while True:
            await ws.send_json(await asyncio.to_thread(runtime.snapshot))
            await asyncio.sleep(1 / 50)

    @app.websocket("/ws")
    async def socket(ws: WebSocket):
        if ws.headers.get("host") != host or ws.headers.get("origin") != origin:
            await ws.close(code=1008)
            return
        await ws.accept()
        owner = object()
        stream = None
        try:
            login = await asyncio.wait_for(ws.receive_text(), timeout=3)
            if len(login) > 128 or not secrets.compare_digest(login.encode(), token.encode()):
                await ws.close(code=1008)
                return
            if not runtime.connect(owner):
                await ws.close(code=1008, reason="Uno Studio è già collegato.")
                return
            stream = asyncio.create_task(send_snapshots(ws))
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
        except (WebSocketDisconnect, asyncio.TimeoutError, ValueError):
            pass
        finally:
            await asyncio.to_thread(runtime.disconnect, owner)
            if stream:
                stream.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await stream

    @app.get("/")
    def studio():
        return FileResponse(STUDIO / "index.html")

    app.mount("/assets", StaticFiles(directory=STUDIO / "assets", check_dir=False))

    return app


def app_from_env():
    return create_app(int(os.environ.get("KINETICDESK_PORT", "5174")))
