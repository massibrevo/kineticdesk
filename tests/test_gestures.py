from dataclasses import replace

from kineticdesk.gestures import GestureEngine, Hand, Profile
from kineticdesk.replay import demo, frame


def feed(engine, name, start, end, **offset):
    hand = Hand.from_points(frame(name, **offset)) if name else None
    return [
        action
        for i in range(round(start * 100), round(end * 100))
        for action in engine.tick(i / 100, hand)
    ]


def ready(profile=None):
    engine = GestureEngine(profile)
    assert not feed(engine, "fist", 0, .90)
    assert engine.mode == "armed"
    assert any(a.kind == "move" for a in feed(engine, "point", .90, 1.05))
    return engine


def kinds(actions):
    return [action.kind for action in actions]


def notable(actions):
    return [kind for kind in kinds(actions) if kind != "move"]


def test_full_replay():
    engine = GestureEngine()
    actions = [
        a for i in range(145) for a in engine.tick(i / 30, Hand.from_points(demo(i / 30)))
    ]
    assert notable(actions)[:3] == ["click", "down", "up"]
    assert len([a for a in actions if a.kind == "click"]) == 1
    assert len([a for a in actions if a.kind == "up"]) == 1
    assert any(a.kind == "scroll" and a.amount < 0 for a in actions)
    down = kinds(actions).index("down")
    up = kinds(actions).index("up")
    assert kinds(actions)[down + 1:up] and set(kinds(actions)[down + 1:up]) == {"move"}
    assert engine.mode == "paused" and engine.reason == "palm"


def test_requires_stable_arm_and_open_point():
    engine = GestureEngine()
    assert not feed(engine, "point", 0, 1)
    assert not feed(engine, "fist", 1, 1.50)
    assert not feed(engine, None, 1.50, 1.53)
    assert not feed(engine, "fist", 1.53, 2.10)
    assert engine.mode == "ready"
    assert not feed(engine, "fist", 2.10, 2.40)
    assert engine.mode == "armed"
    assert not feed(engine, "pinch", 2.40, 3.40)


def test_freeze_between_point_and_scroll():
    engine = ready()
    position = engine.position
    assert not feed(engine, "fist", 1.05, 1.35)
    assert engine.position == position
    assert not feed(engine, "scroll", 1.35, 1.56)
    assert kinds(feed(engine, "scroll", 1.56, 1.72, y=.13)) == ["scroll", "scroll"]
    assert engine.position == position


def test_click_debounce_release_once_with_stationary_pointer():
    engine = ready()
    feed(engine, "point", 1.05, 1.70)
    assert not feed(engine, "pinch", 1.70, 1.74)
    assert not notable(feed(engine, "point", 1.74, 1.92))
    assert not feed(engine, "pinch", 1.92, 2.13)
    assert notable(feed(engine, "point", 2.13, 2.50)) == ["click"]


def test_pause_while_dragging_releases_once():
    engine = ready()
    assert kinds(feed(engine, "pinch", 1.05, 1.63)) == ["down"]
    assert kinds(feed(engine, "palm", 1.63, 1.99)) == ["up"]
    assert not feed(engine, "point", 1.99, 3.0)
    assert engine.mode == "paused"


def test_lost_hand_aborts_drag_and_cannot_rearm():
    engine = ready()
    assert kinds(feed(engine, "pinch", 1.05, 1.63)) == ["down"]
    assert not feed(engine, None, 1.63, 1.75)
    assert kinds(feed(engine, None, 1.75, 1.95)) == ["up"]
    assert engine.reason == "tracking-lost"
    assert not feed(engine, "fist", 1.95, 3.)
    assert engine.mode == "paused"


def test_single_missing_frame_cancels_pending_click():
    engine = ready()
    assert not feed(engine, "pinch", 1.05, 1.25)
    assert not feed(engine, None, 1.25, 1.26)
    assert "click" not in kinds(feed(engine, "point", 1.26, 1.50))


def test_explicit_pause_during_drag_releases_once():
    engine = ready()
    assert kinds(feed(engine, "pinch", 1.05, 1.65)) == ["down"]
    assert kinds(engine.reset(1.66, "paused", "stop")) == ["up"]
    assert not engine.reset(1.67, "paused", "stop")


def test_profile_affects_coordinates_and_hold():
    base = ready()
    alternate = ready(Profile(x_min=.30, x_max=.80, drag_ms=600))
    assert alternate.position[0] < base.position[0]
    assert "down" in kinds(feed(base, "pinch", 1.05, 1.60))
    assert not feed(alternate, "pinch", 1.05, 1.60)
    assert "down" in kinds(feed(alternate, "pinch", 1.60, 1.78))


def test_slightly_bent_index_can_scan_and_move():
    points = frame("point")
    closed = frame("fist")
    for i in range(6, 9):
        points[i] = [a + .4 * (b - a) for a, b in zip(points[i], closed[i])]
    hand = Hand.from_points(points)
    assert hand.point and not hand.palm
    engine = GestureEngine()
    engine.begin(0, "scan", arm_pose="point")
    for i in range(55):
        assert not engine.tick(i / 100, hand)
    assert engine.mode == "ready"
    assert not engine.tick(.55, hand)
    assert engine.mode == "armed"
    assert kinds(engine.tick(.57, hand)) == ["move"]


def test_brief_loose_pinch_clicks_once():
    engine = ready()
    pinch = replace(Hand.from_points(frame("pinch")), pinch=.27)
    for i in range(105, 111):
        assert not engine.tick(i / 100, pinch)
    release = replace(Hand.from_points(frame("point")), pinch=.42)
    events = [event for i in range(111, 150) for event in engine.tick(i / 100, release)]
    assert notable(events) == ["click"]
