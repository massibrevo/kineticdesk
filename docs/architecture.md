# Architecture

```mermaid
flowchart LR
  C[OpenCV capture] --> Q[Latest frame]
  Q --> M[MediaPipe Hand Landmarker]
  M --> G[Gesture engine]
  R[Synthetic landmark replay] --> G
  G --> S[Session runtime]
  S -->|User consent and scan| O[macOS Quartz input]
  S -->|Authenticated WebSocket| U[React Studio]
  U -->|Heartbeat and commands| S
  W[Watchdog] --> S
```

OpenCV captures frames on one thread. MediaPipe processes the newest frame on
another thread. The one-frame buffer lets the capture thread overwrite frames
that inference has yet to pick up. The gesture engine translates landmarks
into input events. Synthetic replay feeds the same engine without a camera.

The runtime uses a lock to coordinate commands, gesture state, input events,
and button release. A watchdog checks the Studio lifecycle signal, pauses on
prolonged tracking loss, and stops stalled camera sessions. The macOS app uses an
AppKit timer to own the approved native desktop session independently of the
WebKit renderer. Closing the Studio window discards its renderer and turns off
preview encoding. An already active session continues through the native
watchdog and can be stopped from the status menu. An unfinished scan is
cancelled. The app keeps a user-initiated activity only while desktop control
is active, with idle system sleep allowed. Sleep, session changes, or a stalled
native event loop end the session.

The browser version uses a WebSocket heartbeat. A browser socket disconnect
stops capture and releases input. Reconnecting restores the Studio connection
without starting a scan.

The Studio receives state updates at up to 30 Hz. The preview encodes at up to
15 Hz and the server sends each image only once per connection. Camera capture
requests 60 fps and uses the rate available from the device. Native input still
follows fresh tracking frames at the detector's rate.

FastAPI serves the compiled Vite interface and WebSocket on one loopback origin.
The macOS app runs the same service in-process on an available loopback port
and displays the Studio in a native WebKit window. The pointer adapter uses
Quartz logical coordinates for the primary display, sends explicit drag events,
and keeps the PyAutoGUI corner fail-safe enabled. Gesture recognition tracks
one hand at a time.

## Model

KineticDesk uses MediaPipe Hand Landmarker float16/1. The model file is 7,819,105
bytes. The bootstrap verifies the file size and checksum before using the
downloaded model. The native build bundles the verified local copy. The Git
repository contains synthetic landmarks and source code.

- [MediaPipe Hand Landmarker documentation](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker?tab=Python)
- [Official model download](https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task)
- SHA-256 `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`
