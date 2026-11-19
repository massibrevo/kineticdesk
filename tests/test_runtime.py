from time import monotonic

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from kineticdesk.api import create_app
from kineticdesk.config import load_profile, save_profile
from kineticdesk.gestures import Action, Profile
from kineticdesk.replay import frame
from kineticdesk.runtime import Runtime


class FakeInput:
    def __init__(self):
        self.events = []
        self.held = False

    def apply(self, action):
        self.events.append(action.kind)
        self.held = action.kind == "down"

    def release(self):
        if self.held:
            self.events.append("up")
            self.held = False


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("KINETICDESK_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("kineticdesk.runtime.capabilities", lambda: {
        "platform": "macOS", "accessibility": True, "camera": "authorized",
    })
    return Runtime(FakeInput)


def test_profile_persistence(runtime):
    profile = Profile(x_min=.25, pinch_in=.20)
    save_profile(profile)
    assert load_profile() == profile


def test_host_origin_token_and_single_client(runtime):
    origin = "http://127.0.0.1:5174"
    app = create_app(runtime=runtime)
    with TestClient(app, base_url=origin) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/session", headers={"host": "external.local"}).status_code == 403
        assert client.get("/api/session", headers={"origin": "https://other.local"}).status_code == 403
        assert client.get("/api/session", headers={"sec-fetch-site": "cross-site"}).status_code == 403
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("ws://127.0.0.1:5174/ws", headers={"origin": "https://other.local"}):
                pass
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("ws://127.0.0.1:5174/ws", headers={"origin": origin}) as ws:
                ws.send_text("wrong")
                ws.receive_json()
        token = client.get("/api/session").json()["token"]
        with client.websocket_connect("ws://127.0.0.1:5174/ws", headers={"origin": origin}) as ws:
            ws.send_text(token)
            assert ws.receive_json()["desktop"] is False
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("ws://127.0.0.1:5174/ws", headers={"origin": origin}) as second:
                    second.send_text(token)
                    second.receive_json()
        assert runtime.source == "off"


def test_scan_requires_consent_and_stable_index_before_input(runtime, monkeypatch):
    class FakeCamera:
        def __init__(self, *_args):
            self.preview = False

        def start(self):
            pass

        def stop(self):
            pass

    monkeypatch.setattr("kineticdesk.runtime.Camera", FakeCamera)
    owner = object()
    runtime.connect(owner)
    runtime.handle(owner, {"command": "scan"})
    assert runtime.camera.preview and runtime.snapshot()["scanning"]
    assert runtime.input is None

    started = monotonic()
    for i in range(20):
        now = started + i / 100
        runtime._observe(now, now, frame("point"), 4 / 3)
    assert 0 < runtime.engine.arm_progress(now) < 1
    assert runtime.input is None

    for i in range(20, 52):
        now = started + i / 100
        runtime._observe(now, now, frame("point", x=.12 * (i % 2)), 4 / 3)
    assert runtime.input is None

    for i in range(52, 130):
        now = started + i / 100
        runtime._observe(now, now, frame("point"), 4 / 3)
        if runtime.input is not None:
            break
    assert not runtime.snapshot()["scanning"]
    assert runtime.input.events == []
    assert runtime.engine.mode == "armed"

    now += .03
    runtime._observe(now, now, frame("point", x=.08), 4 / 3)
    assert runtime.input.events == ["move"]
    assert runtime.snapshot()["events"][-1]["injected"]


def test_hiding_tab_cancels_pending_scan(runtime):
    owner = object()
    runtime.connect(owner)
    runtime.source = "camera"
    runtime.engine.begin(monotonic(), "scan", arm_pose="point")
    runtime.handle(owner, {"command": "tab-hidden"})
    assert runtime.engine.reason == "tab-hidden"
    assert not runtime.snapshot()["scanning"]
    assert runtime.input is None


@pytest.mark.parametrize("reason", ["disconnect", "timeout", "stop", "pause", "camera-stall"])
def test_emergency_paths_release_once(runtime, reason):
    owner = object()
    runtime.connect(owner)
    adapter = FakeInput()
    runtime.input = adapter
    runtime.source = "camera"
    runtime.engine.mode = "dragging"
    now = monotonic()
    runtime.last_frame = now
    runtime._actions([Action(kind="down", at=now)])
    if reason == "disconnect":
        runtime.disconnect(owner)
    elif reason == "timeout":
        runtime.lease -= 2
        runtime.watchdog()
    elif reason == "stop":
        runtime.handle(owner, {"command": "stop"})
    elif reason == "pause":
        runtime.handle(owner, {"command": "pause"})
    elif reason == "camera-stall":
        runtime.last_frame -= 1
        runtime.watchdog()
    runtime.stop()
    assert runtime.input is None
    assert adapter.events == ["down", "up"]


def test_input_failure_releases(runtime):
    class FailingInput(FakeInput):
        def apply(self, action):
            super().apply(action)
            raise RuntimeError("input failure")

    adapter = FailingInput()
    runtime.input = adapter
    runtime.engine.mode = "dragging"
    runtime._actions([Action(kind="down", at=monotonic())])
    assert adapter.events == ["down", "up"]
    assert runtime.input is None
    assert runtime.engine.reason == "input-error"


def test_hiding_tab_keeps_dry_run_and_disarms_desktop(runtime):
    owner = object()
    runtime.connect(owner)
    runtime.source = "camera"
    runtime.handle(owner, {"command": "tab-hidden"})
    assert runtime.engine.mode == "ready"

    adapter = FakeInput()
    runtime.input = adapter
    runtime.engine.mode = "dragging"
    runtime._actions([Action(kind="down", at=monotonic())])
    runtime.handle(owner, {"command": "tab-hidden"})
    assert adapter.events == ["down", "up"]
    assert runtime.engine.reason == "tab-hidden"
    assert runtime.input is None
