# Privacy and security

Frames are captured only after a request from the Studio. No microphone,
screen capture, accounts, analytics, cloud services or runtime model download
are used. The optional JPEG preview is sent only via the authenticated loopback
WebSocket to the connected Studio and is off when a camera session starts.
Frames, landmarks and performance counters remain in memory. Only the calibration
profile is written to disk.

The listener binds to `127.0.0.1`. HTTP Host and Origin are checked, cross-site
session fetches are refused, and WebSocket connections must present the exact
loopback Host, exact same origin and a random per-process token. The server
accepts one Studio client and a fixed command vocabulary. The token is sent
after the WebSocket opens and does not appear in the URL. The UI is served with
a content security policy and the browser itself has camera and microphone
access disabled.

Desktop injection requires a fresh camera frame, Accessibility, UI consent,
and completion of the arm gesture. Palm pause, lease expiry, camera loss and
shutdown release held buttons. Quartz release takes the safety path directly
so a mouse corner does not suppress mouse-up. The OS can reject input if it
revokes permission or changes session. Force-killing a process bypasses normal
cleanup. Use Stop or Ctrl+C for normal shutdown.
