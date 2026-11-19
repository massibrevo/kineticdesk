# Privacy and security

The camera starts only when you request a scan or webcam simulation. Frames,
landmarks, and performance counters stay in memory. The app writes your
calibration profile and language preference to disk. KineticDesk uses local processing without a
microphone, screen capture, accounts, analytics, or runtime model downloads.

A desktop scan opens the camera preview. In simulation, you can show the preview
on demand. The service sends preview frames to the connected Studio through an
authenticated loopback WebSocket.

The service listens on `127.0.0.1`. It validates the HTTP Host and Origin,
rejects cross-site requests for session credentials, and requires the WebSocket
to use the same origin and present a random per-process token. The Studio sends
the token after opening the socket. The service accepts one client and a fixed
set of commands. A content security policy restricts what the Studio can load.
The native WebKit window limits navigation to the local app origin's host.

Desktop input requires fresh camera tracking, Accessibility permission, and
an explicit scan request. The native app can continue an active session with
its window closed and shows camera and input status in the menu bar. Loss of
tracking, a stalled lifecycle check, a browser disconnect, Mac sleep, or quit
releases any held button. The release path
bypasses the corner fail-safe check so it can still send mouse-up. macOS can
reject input after a permission or session change. Use **Stop** or quit normally
to let the app release input and shut down the capture thread.
