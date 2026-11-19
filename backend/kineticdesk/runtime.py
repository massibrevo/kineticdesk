"""Serialize gesture actions, consent, camera changes and emergency release."""
from collections import deque
from threading import RLock
from time import monotonic

from .camera import Camera
from .config import load_profile, save_profile
from .gestures import GestureEngine, Hand, Profile
from .platform_input import MacInput, capabilities
from .replay import demo

LEASE = 1.25
FRAME_TIMEOUT = .35
CAMERA_START_TIMEOUT = 25.


class Runtime:
    def __init__(
        self, input_factory=MacInput, *, open_accessibility=None, accessibility_offered=False,
    ):
        self.lock = RLock()
        self.profile = load_profile()
        self.defaults = Profile().model_dump()
        self.engine = GestureEngine(self.profile)
        self.input_factory = input_factory
        self.open_accessibility = open_accessibility
        self.accessibility_offered = accessibility_offered
        self.awaiting_accessibility = False
        self.input = None
        self.owner = None
        self.lease = 0.
        self.camera = None
        self.retiring = None
        self.source = "off"
        self.source_started = 0.
        self.last_frame = None
        self.points = None
        self.aspect = 4 / 3
        self.preview = None
        self.error = None
        self.history = deque(maxlen=100)
        self.action_id = 0
        self.frames = deque(maxlen=90)
        self.latencies = deque(maxlen=150)
        self.detected = self.total = 0
        self.demo_started = None
        self.device = capabilities()

    def refresh_permissions(self):
        with self.lock:
            self.device = capabilities()
            if self.device["accessibility"]:
                self.awaiting_accessibility = False

    def mark_accessibility_offered(self):
        with self.lock:
            self.accessibility_offered = True

    def _request_accessibility(self, *, manual=False):
        if self.open_accessibility is None or self.device["accessibility"]:
            return
        self.awaiting_accessibility = True
        self.error = None
        if manual or not self.accessibility_offered:
            self.open_accessibility()
            self.accessibility_offered = True

    def connect(self, owner):
        with self.lock:
            if self.owner is not None:
                return False
            self.owner = owner
            self.lease = monotonic()
            return True

    def disconnect(self, owner):
        with self.lock:
            if owner is self.owner:
                self.stop("ui-disconnected")
                self.owner = None

    def _actions(self, actions, frame_at=None):
        for action in actions:
            injected = False
            if self.input is not None:
                try:
                    self.input.apply(action)
                    injected = True
                except Exception as error:
                    self.error = str(error)
                    self._release()
                    self.engine.reset(monotonic(), "paused", "input-error")
                    return
            self.action_id += 1
            item = action.model_dump() | {"id": self.action_id, "injected": injected}
            self.history.append(item)
            if injected and frame_at is not None:
                self.latencies.append((monotonic() - frame_at) * 1000)

    def _release(self):
        if self.input is None:
            return
        try:
            self.input.release()
        except Exception as error:
            self.error = str(error)
            return
        self.input = None

    def _output_available(self):
        return self.input is not None and self.engine.mode in (
            "ready", "armed", "pinching", "dragging",
        )

    def _scanning(self):
        return self.source == "camera" and self.engine.mode == "ready" and (
            self.engine.reason == "scan"
        )

    def _pause(self, reason):
        self._actions(self.engine.reset(monotonic(), "paused", reason))
        self._release()

    def stop(self, reason="stop"):
        with self.lock:
            self._pause(reason)
            self.engine.mode = "stopped"
            self.source = "off"
            self.demo_started = None
            self.points = self.preview = self.last_frame = None
            if self.camera is not None:
                self.camera.stop()
                self.retiring, self.camera = self.camera, None

    def _new_source(self, source):
        self.stop("source-change")
        if self.input is not None:
            raise RuntimeError("Il rilascio del pulsante è ancora in sospeso.")
        self.error = None
        self.frames.clear()
        self.latencies.clear()
        self.history.clear()
        self.detected = self.total = 0
        self.source = source
        self.source_started = monotonic()
        self.engine = GestureEngine(self.profile)

    def handle(self, owner, message):
        with self.lock:
            if owner is not self.owner:
                return
            command = message.get("command")
            now = monotonic()
            if command == "heartbeat":
                self.lease = now
                return
            try:
                self._command(command, message, now)
            except Exception as error:
                self.error = str(error)

    def _command(self, command, message, now):
        if command == "stop":
            self.stop()
        elif command == "pause":
            self._pause("ui-pause")
        elif command == "tab-hidden":
            if self._output_available() or self._scanning():
                self._pause("tab-hidden")
        elif command in ("permissions", "open-accessibility"):
            self.refresh_permissions()
            if command == "open-accessibility":
                self._request_accessibility(manual=True)
        elif command in ("camera", "scan"):
            if command == "scan":
                if now - self.lease >= LEASE:
                    raise RuntimeError("La connessione con lo Studio non è attiva.")
                self.refresh_permissions()
                if not self.device["accessibility"]:
                    if self.open_accessibility is not None:
                        self._request_accessibility()
                        return
                    raise RuntimeError("Concedi Accessibilità al processo di avvio in Impostazioni.")
                if self._output_available() or self._scanning():
                    return
            if self.camera is None:
                self._start_camera()
            if command == "scan":
                self._pause("scan")
                if self.input is not None:
                    raise RuntimeError("Il rilascio del pulsante è ancora in sospeso.")
                self.camera.preview = True
                self.engine.begin(now, "scan", arm_pose="point")
                self.error = None
        elif command == "demo":
            self._new_source("replay")
            self.demo_started = now
        elif command == "preview" and self.camera is not None:
            self.camera.preview = message.get("enabled") is True
            if not self.camera.preview:
                self.preview = None
        elif command == "dry-run" and self.camera is not None:
            self._pause("dry-run")
            if self.input is None:
                self.engine.begin(now, "dry-run")
                self.error = None
        elif command == "profile":
            if self.source != "off":
                raise RuntimeError("Ferma la sorgente prima di salvare la calibrazione.")
            profile = Profile.model_validate(message.get("profile"))
            save_profile(profile)
            self.profile = profile
            self.engine.profile = profile
            self.error = None

    def _start_camera(self):
        if self.retiring is not None and self.retiring.alive:
            raise RuntimeError("La fotocamera si sta chiudendo. Riprova tra un istante.")
        self.device = capabilities()
        self._new_source("camera")
        camera = Camera(self.profile, self._frame, self._camera_error)
        try:
            camera.start()
        except Exception:
            camera.stop()
            self.retiring = camera
            self.stop("camera-error")
            raise
        self.camera = camera

    def _camera_error(self, camera, message):
        with self.lock:
            if camera is self.camera:
                self.device = capabilities()
                self.stop("camera-error")
                self.error = message

    def _frame(self, camera, at, points, aspect, preview):
        with self.lock:
            now = monotonic()
            if camera is not self.camera or now - at > .18:
                return
            if now - self.lease >= LEASE:
                self.stop("ui-timeout")
                return
            if self.last_frame is None:
                self.device = capabilities()
            self.preview = preview if camera.preview else None
            self._observe(now, at, points, aspect)

    def _observe(self, now, at, points, aspect):
        self.aspect, self.last_frame, self.points = aspect, at, points
        hand = Hand.from_points(points, aspect) if points else None
        self.frames.append(at)
        self.total += 1
        self.detected += hand is not None
        scanning = self._scanning()
        actions = self.engine.tick(now, hand)
        if scanning and self.engine.mode == "armed":
            try:
                self.input = self.input_factory()
            except Exception as error:
                self.error = str(error)
                self._pause("input-error")
                return
        self._actions(actions, at)
        if self.engine.mode == "paused":
            self._release()

    def watchdog(self):
        with self.lock:
            now = monotonic()
            if self.input is not None and not self._output_available():
                self._release()
            if self.source == "off":
                return
            if now - self.lease >= LEASE:
                self.stop("ui-timeout")
                return
            if self.demo_started is not None:
                elapsed = now - self.demo_started
                if elapsed > 4.85:
                    self.demo_started = None
                    self.points = None
                else:
                    self._observe(now, now, demo(elapsed), 4 / 3)
            elif self.source == "camera":
                if self.last_frame is not None and now - self.last_frame > FRAME_TIMEOUT:
                    self.stop("camera-stalled")
                    self.error = "La fotocamera ha smesso di inviare fotogrammi."
                elif self.last_frame is None and now - self.source_started > CAMERA_START_TIMEOUT:
                    self.stop("camera-stalled")
                    self.error = "La fotocamera non ha risposto in tempo."
                elif self.last_frame is not None and now - self.last_frame > .09:
                    self._actions(self.engine.tick(now, None))
                    if self.engine.mode == "paused":
                        self._release()

    def snapshot(self):
        with self.lock:
            now = monotonic()
            fifo = [stamp for stamp in self.frames if now - stamp <= 1.25]
            rate = (len(fifo) - 1) / (fifo[-1] - fifo[0]) if len(fifo) > 1 else None
            latency = sorted(self.latencies)
            return {
                "source": self.source, "mode": self.engine.mode, "reason": self.engine.reason,
                "desktop": self._output_available(), "position": self.engine.position,
                "pose": self.engine.pose, "armProgress": self.engine.arm_progress(now),
                "scanning": self._scanning(),
                "points": self.points, "aspect": self.aspect, "preview": self.preview,
                "previewEnabled": self.camera is not None and self.camera.preview,
                "events": list(self.history), "device": self.device, "error": self.error,
                "canOpenAccessibility": self.open_accessibility is not None,
                "awaitingAccessibility": self.awaiting_accessibility,
                "profile": self.profile.model_dump(), "defaults": self.defaults, "fps": rate,
                "frameAge": (now - self.last_frame) * 1000 if self.last_frame is not None else None,
                "tracking": self.detected / self.total if self.total else None,
                "latency": [latency[len(latency) // 2], latency[int(.95 * (len(latency) - 1))]]
                if latency else None,
            }
