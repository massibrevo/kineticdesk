from time import monotonic

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from kineticdesk.api import create_app
from kineticdesk.config import load_language, load_profile, save_profile
from kineticdesk.gestures import Action, Profile
from kineticdesk.replay import frame
from kineticdesk.runtime import LEASE, Runtime


class FakeInput:
    def __init__(self):
        self.events = []
        self.held = False

    def apply(self, action):
        self.events.append(action.kind)
        if action.kind in ("down", "up"):
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
        runtime.lease -= LEASE + .1
        runtime.watchdog()
        assert runtime.engine.reason == "ui-timeout"
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


@pytest.mark.parametrize("already_offered", [False, True])
def test_missing_accessibility_offers_pane_once(runtime, monkeypatch, already_offered):
    opened = []
    runtime.open_accessibility = lambda: opened.append(True)
    runtime.accessibility_offered = already_offered
    denied = runtime.device | {"accessibility": False}
    monkeypatch.setattr("kineticdesk.runtime.capabilities", lambda: denied)
    owner = object()
    runtime.connect(owner)

    runtime.handle(owner, {"command": "scan"})
    runtime.handle(owner, {"command": "scan"})

    automatic_opens = 0 if already_offered else 1
    assert opened == [True] * automatic_opens
    assert runtime.snapshot()["awaitingAccessibility"]
    assert runtime.source == "off"
    assert runtime.camera is None and runtime.input is None

    runtime.handle(owner, {"command": "open-accessibility"})
    assert opened == [True] * (automatic_opens + 1)
    runtime.handle(owner, {"command": "scan"})
    assert opened == [True] * (automatic_opens + 1)

    monkeypatch.setattr("kineticdesk.runtime.capabilities", lambda: denied | {"accessibility": True})
    runtime.refresh_permissions()
    assert not runtime.snapshot()["awaitingAccessibility"]
    assert runtime.camera is None and runtime.input is None


def test_camera_frame_stall_freezes_then_resumes_before_safety_pause(runtime, monkeypatch):
    owner = object()
    runtime.connect(owner)
    camera = type("Camera", (), {"preview": False})()
    runtime.camera = camera
    runtime.source = "camera"
    runtime.engine.mode = "armed"
    adapter = FakeInput()
    runtime.input = adapter
    now = monotonic()
    runtime.engine.last_active = now
    monkeypatch.setattr("kineticdesk.runtime.monotonic", lambda: now)
    for offset in (0., .04, .08):
        now = runtime.lease + offset
        runtime._frame(camera, now, frame("point"), 4 / 3, None)
    adapter.events.clear()
    now += .17
    runtime.watchdog()
    assert runtime.snapshot()["trackingInterrupted"]
    assert runtime.input is adapter and adapter.events == []

    now += .01
    runtime._frame(camera, now, frame("point", x=.08), 4 / 3, None)
    assert not runtime.snapshot()["trackingInterrupted"]
    assert adapter.events == ["move"]

    now += runtime.engine.LOST + .01
    runtime.watchdog()
    assert runtime.engine.reason == "tracking-lost"
    assert runtime.input is None


class BackgroundCamera:
    def __init__(self):
        self.preview = True
        self.stopped = False

    def stop(self):
        self.stopped = True


def arm_native_drag(runtime):
    runtime.native_window = True
    owner = object()
    runtime.connect(owner)
    runtime.engine.mode = "dragging"
    runtime.source = "camera"
    runtime.camera = BackgroundCamera()
    runtime.preview_requested = True
    adapter = FakeInput()
    runtime.input = adapter
    now = monotonic()
    runtime.engine.last_seen = runtime.last_frame = runtime.engine.last_active = now
    runtime._actions([Action(kind="down", at=now)])
    return owner, adapter, runtime.camera


def test_native_session_survives_window_close_and_studio_reconnect(runtime, monkeypatch):
    owner, adapter, camera = arm_native_drag(runtime)
    now = monotonic()
    monkeypatch.setattr("kineticdesk.runtime.monotonic", lambda: now)
    runtime.set_native_background(True)
    runtime.detach_studio()
    runtime.disconnect(owner)
    assert runtime.snapshot_for(owner) is None
    assert runtime.health()["background"] and runtime.health()["desktop"]
    assert not runtime.health()["studioConnected"]
    assert not camera.preview and not camera.stopped

    for _ in range(10):
        now = runtime.lease + .35
        runtime.last_frame = runtime.engine.last_seen = now
        runtime.engine.last_active = now
        runtime.pulse_native_window()
        runtime.watchdog()
        assert runtime.input is adapter
    assert adapter.events == ["down"]
    now += .04
    runtime._frame(camera, now, frame("pinch", x=.05), 4 / 3, None)
    assert adapter.events == ["down", "move"]

    runtime.set_native_background(False)
    new_owner = object()
    assert runtime.connect(new_owner)
    assert camera.preview and runtime.snapshot_for(new_owner)["desktop"]
    runtime.stop()
    assert adapter.events == ["down", "move", "up"]
    assert camera.stopped


def test_background_studio_cannot_complete_an_unconfirmed_scan(runtime):
    runtime.native_window = True
    owner = object()
    runtime.connect(owner)
    runtime.camera = camera = BackgroundCamera()
    runtime.source = "camera"
    runtime.engine.begin(monotonic(), "scan", arm_pose="point")

    runtime.set_native_background(True)
    runtime.handle(owner, {"command": "scan"})
    assert camera.stopped
    assert not runtime.snapshot()["scanning"]
    assert runtime.input is None


@pytest.mark.parametrize("cause", ["menu-pause", "system-suspension", "lease", "tracking-loss"])
def test_native_background_exits_safely_without_a_studio_connection(runtime, monkeypatch, cause):
    _owner, adapter, camera = arm_native_drag(runtime)
    now = runtime.lease
    monkeypatch.setattr("kineticdesk.runtime.monotonic", lambda: now)
    runtime.set_native_background(True)
    runtime.detach_studio()
    if cause == "menu-pause":
        runtime.pause_desktop()
    elif cause == "system-suspension":
        runtime.stop("system-suspension")
    elif cause == "lease":
        now += LEASE + .1
        runtime.watchdog()
        assert runtime.engine.reason == "ui-timeout"
    else:
        now = runtime.last_frame + runtime.engine.LOST + .01
        runtime.watchdog()
        assert runtime.engine.reason == "tracking-lost"
    assert adapter.events == ["down", "up"]
    assert camera.stopped and runtime.input is None
    runtime.pulse_native_window()
    assert not runtime.health()["desktop"]


def test_studio_language_is_persisted_without_resuming_input(runtime):
    owner = object()
    assert load_language() == "en"
    runtime.connect(owner)
    runtime.handle(owner, {"command": "language", "language": "it"})
    assert runtime.snapshot()["language"] == load_language() == "it"
    runtime.handle(owner, {"command": "language", "language": "unknown"})
    assert runtime.snapshot()["language"] == "it"
    assert runtime.input is None


def test_expired_studio_cannot_reclaim_or_stop_a_new_connection(runtime, monkeypatch):
    old, new = object(), object()
    assert runtime.connect(old)
    now = runtime.lease + LEASE + .1
    monkeypatch.setattr("kineticdesk.runtime.monotonic", lambda: now)
    runtime.handle(old, {"command": "heartbeat"})
    assert runtime.connect(new)
    assert runtime.snapshot_for(old) is None
    runtime.disconnect(old)
    assert runtime.snapshot_for(new)["source"] == "off"
    assert runtime.engine.reason == "ui-timeout"
