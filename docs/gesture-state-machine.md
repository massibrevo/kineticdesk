# Gesture state machine

Each frame provides 21 timestamped hand landmarks. The engine normalizes the
thumb-to-index distance by averaging palm width and wrist-to-middle-knuckle
distance. It uses finger straightness and reach from the wrist to recognize an
extended finger. It also accounts for the frame aspect ratio and the profile's
mirroring setting.

| State | Input | Result |
| --- | --- | --- |
| Off | Start simulation or replay | Wait for the dry-run gesture. |
| Off or dry-run | Request a desktop scan with Accessibility permission | Show the preview and start scanning. |
| Waiting in dry-run | Hold a fist for 750 ms | Arm the simulated pointer. |
| Scanning | Hold an extended index finger steady for 550 ms of fresh tracking | Enable desktop pointer control. |
| Armed | Point for 35 ms | Move the pointer with adaptive smoothing. |
| Armed | Close the thumb-to-index pinch shortly after pointing | Freeze the pointer and begin timing the pinch. |
| Pinching | Open before 55 ms, or lose tracking | Cancel the pending click. |
| Pinching | Open after reaching 55 ms and before the drag threshold, then stay open for 27 ms | Click once and return to Armed. |
| Pinching | Hold until the drag threshold, 400 ms by default | Press the mouse button once and enter Dragging. |
| Dragging | Maintain the pinch | Move relative to the hand position at the start of the drag. |
| Dragging | Keep the pinch open for 27 ms | Release the mouse button once and return to Armed. |
| Armed | Extend index and middle for 90 ms and move vertically | Scroll at a limited rate while keeping the pointer still. |
| Armed, Pinching, or Dragging | Open palm for 105 ms, lose tracking for 200 ms, or remain idle for 45 seconds | Release any held button and pause. |
| Scanning or controlling the desktop | Hide the Studio tab | Cancel the scan or release any held button and pause. |
| Any | Stop, disconnect, heartbeat expires, camera fails, or the app quits | Release any held button, stop, and discard consent. |
| Paused | Start simulation or request a new scan | Wait for the corresponding activation gesture. |

The pinch uses separate thresholds for closing and opening to avoid repeated
events near the boundary. An open palm takes priority over clicking and dragging.
After a click or drag, point with an open pinch before starting another pinch.
