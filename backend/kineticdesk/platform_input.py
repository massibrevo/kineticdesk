"""macOS desktop input, lazily loaded after explicit UI consent."""
import ctypes
import platform
from functools import lru_cache


@lru_cache(maxsize=1)
def _accessibility_check():
    library = ctypes.CDLL(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices",
    )
    check = library.AXIsProcessTrusted
    check.argtypes = []
    check.restype = ctypes.c_bool
    return check


def accessibility_trusted():
    return _accessibility_check()()


def capabilities():
    if platform.system() != "Darwin":
        return {"platform": platform.system(), "accessibility": False, "camera": "unknown"}
    try:
        import AVFoundation as av

        camera = {
            0: "not-requested", 1: "restricted", 2: "denied", 3: "authorized",
        }.get(av.AVCaptureDevice.authorizationStatusForMediaType_(av.AVMediaTypeVideo), "unknown")
        return {
            "platform": "macOS", "accessibility": accessibility_trusted(), "camera": camera,
        }
    except (ImportError, OSError, AttributeError):
        return {"platform": "macOS", "accessibility": False, "camera": "unknown"}


class MacInput:
    def __init__(self):
        import pyautogui
        import Quartz as q

        if not accessibility_trusted():
            raise RuntimeError("Abilita Accessibilità per il processo di avvio in Impostazioni.")
        pyautogui.FAILSAFE = True
        self.pyautogui, self.q = pyautogui, q
        display = q.CGMainDisplayID()
        self.bounds = q.CGDisplayBounds(display)
        self.held = False

    def _location(self):
        return self.q.CGEventGetLocation(self.q.CGEventCreate(None))

    def _mouse(self, kind, at):
        q = self.q
        event = q.CGEventCreateMouseEvent(None, kind, at, q.kCGMouseButtonLeft)
        if event is None:
            raise RuntimeError("Core Graphics non ha creato l’evento del mouse.")
        q.CGEventPost(q.kCGHIDEventTap, event)

    def release(self):
        if self.held:
            self._mouse(self.q.kCGEventLeftMouseUp, self._location())
            self.held = False

    def apply(self, action):
        q = self.q
        if action.kind == "up":
            self.release()
            return
        self.pyautogui.failSafeCheck()
        if self.pyautogui.FAILSAFE:
            point = self._location()
            origin, size = self.bounds.origin, self.bounds.size
            at_x_edge = int(point.x - origin.x) in (0, int(size.width) - 1)
            at_y_edge = int(point.y - origin.y) in (0, int(size.height) - 1)
            if at_x_edge and at_y_edge:
                raise self.pyautogui.FailSafeException("Angolo di emergenza del display.")
        if not accessibility_trusted():
            raise RuntimeError("Il permesso Accessibilità non è più disponibile.")
        if action.kind == "move":
            origin, size = self.bounds.origin, self.bounds.size
            at = (
                origin.x + 2 + action.x * (size.width - 5),
                origin.y + 2 + action.y * (size.height - 5),
            )
            event = q.kCGEventLeftMouseDragged if self.held else q.kCGEventMouseMoved
            self._mouse(event, at)
        elif action.kind in ("down", "click"):
            self.held = True
            self._mouse(q.kCGEventLeftMouseDown, self._location())
            if action.kind == "click":
                self.release()
        elif action.kind == "scroll":
            event = q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitLine, 1, action.amount)
            if event is None:
                raise RuntimeError("Core Graphics non ha creato l’evento di scorrimento.")
            q.CGEventPost(q.kCGHIDEventTap, event)
