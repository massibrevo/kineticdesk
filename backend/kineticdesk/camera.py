"""Exclusive camera ownership and one-slot handoff to the detector."""
import logging
import sys
import threading
import time

from .assets import MODEL
from .errors import StudioError

FIRST_FRAME_TIMEOUT = 4.0
FRAME_TIMEOUT = .85
TARGET_CAMERA_FPS = 60
PREVIEW_PERIOD = 1 / 15
logger = logging.getLogger(__name__)


class Camera:
    def __init__(self, profile, on_frame, on_error):
        self.profile, self.on_frame, self.on_error = profile, on_frame, on_error
        self.done = threading.Event()
        self.condition = threading.Condition()
        self.frame = None
        self.preview = False
        self.capture = threading.Thread(target=self._capture, daemon=True, name="camera")
        self.detector = threading.Thread(target=self._detect, daemon=True, name="landmarks")

    def start(self):
        if not MODEL.is_file():
            raise StudioError("model-missing")
        self.capture.start()
        self.detector.start()

    @property
    def alive(self):
        return self.capture.is_alive() or self.detector.is_alive()

    def stop(self):
        self.done.set()
        with self.condition:
            self.condition.notify_all()

    def _failed(self, error):
        if not self.done.is_set():
            self.stop()
            if not isinstance(error, StudioError):
                logger.exception("Camera worker failed", exc_info=error)
                error = StudioError("camera-unavailable")
            self.on_error(self, str(error))

    def _capture(self):
        device = None
        try:
            import cv2

            backend = cv2.CAP_ANY
            if sys.platform == "darwin":
                self._request_macos_video()
                backend = cv2.CAP_AVFOUNDATION
            if self.done.is_set():
                return
            device = cv2.VideoCapture(self.profile.camera, backend)
            if not device.isOpened():
                raise StudioError("camera-unavailable")
            device.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            device.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            device.set(cv2.CAP_PROP_FPS, TARGET_CAMERA_FPS)
            first_frame_deadline = time.monotonic() + FIRST_FRAME_TIMEOUT
            last_capture = None
            while not self.done.is_set():
                ok, frame = device.read()
                at = time.monotonic()
                if not ok or frame is None or not frame.size:
                    if last_capture is None and at >= first_frame_deadline:
                        raise StudioError("camera-no-frames")
                    if last_capture is not None and at - last_capture >= FRAME_TIMEOUT:
                        raise StudioError("camera-stream-lost")
                    self.done.wait(.03)
                    continue
                last_capture = at
                with self.condition:
                    self.frame = at, frame
                    self.condition.notify()
        except Exception as error:
            self._failed(error)
        finally:
            if device is not None:
                device.release()

    def _request_macos_video(self):
        import AVFoundation as av

        status = av.AVCaptureDevice.authorizationStatusForMediaType_(av.AVMediaTypeVideo)
        if status == 0:
            replied = threading.Event()
            granted = False

            def permission_result(allowed):
                nonlocal granted
                granted = allowed
                replied.set()

            av.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                av.AVMediaTypeVideo, permission_result,
            )
            deadline = time.monotonic() + 20
            while not self.done.is_set() and not replied.wait(.1):
                if time.monotonic() >= deadline:
                    raise StudioError("camera-permission-timeout")
            if granted or self.done.is_set():
                return
        if status != 3:
            raise StudioError("camera-permission-required")

    def _detect(self):
        try:
            import base64

            import cv2
            import mediapipe as mp

            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=1,
                min_hand_detection_confidence=.58, min_tracking_confidence=.53,
            )
            last_ms = -1
            preview = None
            preview_at = 0.
            with mp.tasks.vision.HandLandmarker.create_from_options(options) as tracker:
                while not self.done.is_set():
                    with self.condition:
                        self.condition.wait_for(
                            lambda: self.frame is not None or self.done.is_set(),
                        )
                        if self.done.is_set():
                            break
                        at, frame = self.frame
                        self.frame = None
                    if time.monotonic() - at > .18:
                        continue
                    if self.profile.mirrored:
                        frame = cv2.flip(frame, 1)
                    image = mp.Image(
                        image_format=mp.ImageFormat.SRGB,
                        data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
                    )
                    last_ms = max(last_ms + 1, round(at * 1000))
                    found = tracker.detect_for_video(image, last_ms)
                    points = [[p.x, p.y, p.z] for p in found.hand_landmarks[0]] if (
                        found.hand_landmarks
                    ) else None
                    if not self.preview:
                        preview = None
                    elif preview is None or at - preview_at >= PREVIEW_PERIOD:
                        height, width = frame.shape[:2]
                        scale = min(1., 480 / max(width, height))
                        thumbnail = cv2.resize(frame, (round(width * scale), round(height * scale)),
                                               interpolation=cv2.INTER_AREA)
                        ok, jpg = cv2.imencode(".jpg", thumbnail, [cv2.IMWRITE_JPEG_QUALITY, 68])
                        if ok:
                            preview = base64.b64encode(jpg).decode("ascii")
                            preview_at = at
                    self.on_frame(self, at, points, frame.shape[1] / frame.shape[0], preview)
        except Exception as error:
            self._failed(error)
