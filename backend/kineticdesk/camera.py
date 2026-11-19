"""Exclusive camera ownership and one-slot handoff to the detector."""
import sys
import threading
import time
from pathlib import Path

FIRST_FRAME_TIMEOUT = 4.0
MODEL = Path(__file__).resolve().parents[2] / ".cache/models/hand_landmarker.task"


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
            raise RuntimeError("Modello mancante. Esegui scripts/bootstrap.py.")
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
                raise RuntimeError("Fotocamera non disponibile. Controlla dispositivo e permessi.")
            device.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            device.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            misses = 0
            first_frame_deadline = time.monotonic() + FIRST_FRAME_TIMEOUT
            received_frame = False
            while not self.done.is_set():
                ok, frame = device.read()
                at = time.monotonic()
                if not ok or frame is None or not frame.size:
                    if not received_frame and at >= first_frame_deadline:
                        raise RuntimeError("La fotocamera si è aperta ma non invia fotogrammi.")
                    misses += 1
                    if received_frame and misses >= 8:
                        raise RuntimeError("Flusso fotocamera interrotto.")
                    self.done.wait(.03)
                    continue
                received_frame = True
                misses = 0
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
                    raise RuntimeError("Richiesta Fotocamera scaduta. Premi Avvia per riprovare.")
            if granted or self.done.is_set():
                return
        if status != 3:
            raise RuntimeError("Abilita Fotocamera per il processo di avvio in Impostazioni.")

    def _detect(self):
        try:
            import base64

            import cv2
            import mediapipe as mp

            options = mp.tasks.vision.HandLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO, num_hands=1,
                min_hand_detection_confidence=.62, min_tracking_confidence=.60,
            )
            last_ms = -1
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
                    preview = None
                    if self.preview:
                        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 68])
                        if ok:
                            preview = base64.b64encode(jpg).decode("ascii")
                    self.on_frame(self, at, points, frame.shape[1] / frame.shape[0], preview)
        except Exception as error:
            self._failed(error)
