# Gesture state machine

The engine accepts timestamped 21-point landmarks. It normalizes pinch distance
by the mean of palm width and wrist-to-middle-knuckle distance. Finger extension
uses chain straightness and distance from the wrist. The camera frame coordinates
are aspect-corrected for geometry and mirrored according to the profile.

| State | Condition | Output / next state |
| --- | --- | --- |
| Off | Simulation or replay explicitly started | Ready in dry-run |
| Off or dry-run | Explicit scan request with Accessibility | Camera preview and desktop scan, no OS events |
| Ready in dry-run | Continuous fist for 750 ms | Armed, awaiting an open pointing pose |
| Desktop scan | Extended index held steady for 550 ms of fresh tracking | Create OS adapter and arm pointer control |
| Armed | Open pointing pose for 35 ms | Cursor movement with adaptive smoothing |
| Armed | Index/thumb distance below the close threshold immediately after pointing | Freeze the cursor and enter Pinching |
| Pinching | Opens before 55 ms or tracking is interrupted | Cancel pending click |
| Pinching | Opens after 55 ms and before the drag threshold, stable for 27 ms | One click, then Armed |
| Pinching | Stays closed for the drag dwell, 400 ms by default | One mouse-down and enter Dragging |
| Dragging | Pinch remains held | Cursor follows wrist displacement from the drag anchor |
| Dragging | Pinch opens and remains open for 27 ms | One mouse-up, then Armed |
| Armed | Index and middle stable for 90 ms, with sufficient vertical displacement | Rate-limited scroll, cursor frozen |
| Armed, Pinching, Dragging | Open palm for 105 ms, tracking gap of 200 ms, or 45 s idle | Release a held button and pause |
| Any | Stop, UI disconnect or lease expiry, camera failure or shutdown | Release, discard consent and stop |
| Desktop scan or armed desktop | Browser tab hidden | Cancel scan or disarm and release |
| Paused | Explicit dry-run or fresh scan | Ready with fresh arming dwell |

Separate close/open thresholds suppress noise around the pinch boundary.
Open-palm recognition preempts drag and click handling. After a click or drag,
the pointer must be engaged again with an open index pose before another pinch.
