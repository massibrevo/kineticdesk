"""Pure landmark geometry and deterministic gesture transitions."""
from dataclasses import dataclass
from math import dist, isfinite

from pydantic import BaseModel, Field, model_validator


class Profile(BaseModel):
    x_min: float = Field(.10, ge=0, le=.85)
    x_max: float = Field(.90, ge=.15, le=1)
    y_min: float = Field(.09, ge=0, le=.85)
    y_max: float = Field(.89, ge=.15, le=1)
    pinch_in: float = Field(.29, ge=.08, le=.65)
    pinch_out: float = Field(.40, ge=.12, le=.85)
    drag_ms: int = Field(400, ge=300, le=900)
    smoothing: float = Field(.55, ge=.1, le=.95)
    scroll_gain: float = Field(48, ge=15, le=100)
    mirrored: bool = True
    camera: int = Field(0, ge=0, le=9)

    @model_validator(mode="after")
    def validate_ranges(self):
        if min(self.x_max - self.x_min, self.y_max - self.y_min) < .14:
            raise ValueError("The tracking area is too small")
        if self.pinch_out - self.pinch_in < .035:
            raise ValueError("The open-pinch threshold must exceed the closed-pinch threshold")
        return self


class Action(BaseModel):
    kind: str
    at: float
    x: float | None = None
    y: float | None = None
    amount: int | None = None
    interrupted: bool = False


Point = tuple[float, float]


@dataclass(frozen=True)
class Hand:
    tip: Point
    wrist: Point
    scroll_y: float
    pinch: float
    index: bool
    middle: bool
    ring: bool
    pinky: bool
    palm_open: bool | None = None

    @classmethod
    def from_points(cls, points: list[list[float]], aspect: float = 4 / 3):
        if len(points) != 21 or any(len(p) != 3 for p in points):
            return None
        if not all(isfinite(v) for p in points for v in p):
            return None
        xyz = [(x * aspect, y, z * aspect) for x, y, z in points]
        scale = (dist(xyz[5], xyz[17]) + dist(xyz[0], xyz[9])) / 2
        if scale < .025:
            return None

        def extension(i):
            a, b, c, d = xyz[i:i + 4]
            length = dist(a, b) + dist(b, c) + dist(c, d)
            reach = (dist(xyz[0], d) - dist(xyz[0], b)) / scale
            return (dist(a, d) / length if length else 0.), reach

        index, middle, ring, pinky = (extension(i) for i in (5, 9, 13, 17))

        def extended(measures, straightness, reach):
            return measures[0] > straightness and measures[1] > reach

        return cls(
            tuple(points[8][:2]), tuple(points[0][:2]), (points[8][1] + points[12][1]) / 2,
            dist(xyz[4], xyz[8]) / scale,
            extended(index, .72, .08),
            extended(middle, .78, .12),
            extended(ring, .84, .15),
            extended(pinky, .84, .15),
            all(extended(finger, .76, .085) for finger in (index, middle, ring, pinky)),
        )

    @property
    def point(self):
        return self.index and not (self.middle or self.ring or self.pinky)

    @property
    def scroll(self):
        return self.index and self.middle and not (self.ring or self.pinky)

    @property
    def palm(self):
        spread = self.palm_open
        if spread is None:
            spread = self.index and self.middle and self.ring and self.pinky
        return spread and self.pinch > .55

    @property
    def fist(self):
        return not (self.index or self.middle or self.ring or self.pinky)


def clamp(value):
    return min(1., max(0., value))


class GestureEngine:
    ARM = .75
    SCAN = .55
    PAUSE = .175
    DRAG_LOST = .11
    LOST = .75
    IDLE = 45.
    DEBOUNCE = .055
    RELEASE = .027
    POINT = .035
    SCROLL = .09
    MIN_SCROLL = .030
    MIN_MOVE = .010
    MAX_POINTER_SPEED = 3.6  # Normalized screen lengths per second.

    def __init__(self, profile=None):
        self.profile = profile or Profile()
        self.mode = "ready"
        self.reason = "dry-run"
        self.position = (.5, .5)
        self.last_seen = None
        self.last_active = 0.
        self.started = 0.
        self.pointer_sample = None
        self.tracking_interrupted = False
        self.last_point = -1.
        self.pose = ""
        self.pose_since = 0.
        self.arm_pose = "fist"
        self.scan_anchor = None
        self.palm_since = None
        self.release_since = None
        self.scroll_y = None
        self.scroll_accum = 0.
        self.last_scroll = -1.
        self.pinch_wrist = (0., 0.)
        self.pinch_anchor = (.5, .5)
        self.resume_gate = True

    def reset(self, now, mode="ready", reason="dry-run"):
        events = [self._position_action("up", now, interrupted=True)] if self.mode == "dragging" else []
        self.mode, self.reason = mode, reason
        self.pose = ""
        self.scan_anchor = None
        self.palm_since = self.release_since = self.scroll_y = None
        self.scroll_accum = 0.
        self.resume_gate = True
        self.last_seen = None
        self.last_point = -1.
        self.pointer_sample = None
        self.tracking_interrupted = False
        return events

    def begin(self, now, reason="dry-run", arm_pose="fist"):
        self.arm_pose = arm_pose
        return self.reset(now, "ready", reason)

    @property
    def arm_duration(self):
        return self.SCAN if self.arm_pose == "point" else self.ARM

    def arm_progress(self, now):
        if self.mode == "ready" and self.pose == self.arm_pose:
            return min(1., max(0., (now - self.pose_since) / self.arm_duration))
        return 0.

    def _position_action(self, kind, now, interrupted=False):
        return Action(kind=kind, at=now, x=self.position[0], y=self.position[1],
                      interrupted=interrupted)

    def _move(self, now, point):
        elapsed = now - self.pointer_sample if self.pointer_sample is not None else 1 / 30
        if elapsed < self.MIN_MOVE:
            return []
        self.pointer_sample = now
        elapsed = min(elapsed, 1 / 20)
        error = dist(self.position, point)
        if error < .001:
            return []

        # Filter small jitter, but give deliberate movement a faster response.
        # Normalize the weight to elapsed time so camera cadence has less effect.
        fine_weight = self.profile.smoothing * .42
        response = fine_weight + (.93 - fine_weight) * min(1., error / .10)
        weight = min(1 - (1 - response) ** (elapsed * 30), self.MAX_POINTER_SPEED * elapsed / error)
        x, y = (a + weight * (b - a) for a, b in zip(self.position, point))
        if dist(self.position, (x, y)) < .0006:
            return []
        self.position = (x, y)
        self.last_active = now
        return [Action(kind="move", at=now, x=x, y=y)]

    def tick(self, now, hand):
        if self.mode in ("paused", "stopped"):
            return []
        if self.mode != "ready" and now - self.last_active >= self.IDLE:
            return self.reset(now, "paused", "idle")
        gap = now - self.last_seen if self.last_seen is not None else 0.
        if self.mode != "ready" and gap >= self.LOST:
            return self.reset(now, "paused", "tracking-lost")

        if self.mode == "dragging" and gap >= self.DRAG_LOST:
            self.mode = "armed"
            self.resume_gate = True
            self.release_since = None
            self.last_point = -1.
            self.pointer_sample = None
            self.pose = ""
            self.tracking_interrupted = hand is None
            if hand is not None:
                self.last_seen = now
            return [self._position_action("up", now, interrupted=True)]

        if hand is None:
            self.tracking_interrupted = self.mode != "ready"
            if self.mode == "ready" or self.pose != "point":
                self.pose = ""
            self.release_since = self.palm_since = self.scroll_y = None
            self.scroll_accum = 0.
            self.pointer_sample = None
            self.last_point = -1.
            self.resume_gate = True
            if self.mode == "pinching":
                self.mode = "armed"
            return []

        self.last_seen = now
        self.tracking_interrupted = False
        if hand.palm:
            if self.palm_since is None:
                self.palm_since = now
            self.pose = ""
            self.pointer_sample = None
            self.last_point = -1.
            self.release_since = self.scroll_y = None
            self.scroll_accum = 0.
            if self.mode == "pinching":
                self.mode = "armed"
                self.resume_gate = True
            if self.mode != "ready" and now - self.palm_since >= self.PAUSE:
                return self.reset(now, "paused", "palm")
            return []
        self.palm_since = None
        profile = self.profile
        if self.mode in ("pinching", "dragging"):
            return self._pinch(now, hand)
        pose = "fist" if hand.fist else "point" if hand.point else "scroll" if hand.scroll else ""
        if self.mode == "ready" and self.arm_pose == "point":
            if pose != "point" or hand.pinch < profile.pinch_out:
                pose = ""
                self.scan_anchor = None
            elif self.pose != "point" or dist(self.scan_anchor, hand.tip) > .095:
                self.scan_anchor = hand.tip
                self.pose_since = now
        if pose != self.pose:
            self.pose, self.pose_since = pose, now
            self.pointer_sample = None
            self.scroll_y = None
            self.scroll_accum = 0.
        age = now - self.pose_since
        if self.mode == "ready":
            if pose == self.arm_pose and age >= self.arm_duration:
                self.mode, self.reason = "armed", "armed"
                self.last_active = now
                self.resume_gate = self.arm_pose != "point"
            return []
        if self.resume_gate:
            if pose == "point" and hand.pinch >= profile.pinch_out and age >= self.POINT:
                self.resume_gate = False
            else:
                return []
        if hand.pinch <= profile.pinch_in and not (hand.middle or hand.ring or hand.pinky):
            # A fist away from a current or recently engaged pointer cannot start a pinch.
            if now - self.last_point < .18:
                self.mode, self.started = "pinching", now
                self.pinch_anchor, self.pinch_wrist = self.position, hand.wrist
                return []
        if pose == "point" and age >= self.POINT and hand.pinch >= profile.pinch_out:
            self.last_point = now
            return self._move(now, (
                clamp((hand.tip[0] - profile.x_min) / (profile.x_max - profile.x_min)),
                clamp((hand.tip[1] - profile.y_min) / (profile.y_max - profile.y_min)),
            ))
        if pose == "scroll" and age >= self.SCROLL and hand.pinch >= profile.pinch_out:
            return self._scroll(now, hand.scroll_y)
        return []

    def _pinch(self, now, hand):
        profile = self.profile
        if hand.pinch >= profile.pinch_out:
            if self.release_since is None:
                self.release_since = now
            if now - self.release_since < self.RELEASE:
                return []
            held = self.release_since - self.started
            self.release_since = None
            self.pose = ""
            self.resume_gate = True
            dragging = self.mode == "dragging"
            self.mode = "armed"
            self.last_active = now
            if dragging:
                return [self._position_action("up", now)]
            if self.DEBOUNCE <= held < profile.drag_ms / 1000:
                return [self._position_action("click", now)]
            return []
        if self.release_since is not None:
            self.release_since = None
            if hand.pinch > profile.pinch_in:
                return []
        if self.mode == "pinching":
            if now - self.started < profile.drag_ms / 1000:
                return []
            self.mode = "dragging"
            self.last_active = now
            return [self._position_action("down", now)]
        return self._move(now, (
            clamp(self.pinch_anchor[0] + (hand.wrist[0] - self.pinch_wrist[0])
                  / (profile.x_max - profile.x_min)),
            clamp(self.pinch_anchor[1] + (hand.wrist[1] - self.pinch_wrist[1])
                  / (profile.y_max - profile.y_min)),
        ))

    def _scroll(self, now, y):
        if self.scroll_y is None:
            self.scroll_y = y
            return []
        delta = self.scroll_y - y
        self.scroll_y = y
        self.scroll_accum += delta * self.profile.scroll_gain
        if abs(self.scroll_accum) < 1 or now - self.last_scroll < self.MIN_SCROLL:
            return []
        amount = max(-3, min(3, int(self.scroll_accum)))
        self.scroll_accum -= amount
        self.last_scroll = self.last_active = now
        return [Action(kind="scroll", at=now, amount=amount)]
