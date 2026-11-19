# Calibration and webcam check

These instructions use the default English labels. The **Language** selector
switches the Studio to Italian.

1. Select **Simulation only** to start the webcam. Position
   the camera around eye level, use diffuse lighting, and keep your second hand
   outside the frame.
2. Hold a fist until the progress bar fills. Point toward all four edges of
   the tracking guide. If you have to reach too far to cover the practice area,
   stop the session and narrow the bounds in **Calibration**.
   Narrower bounds map less hand movement to the full output area.
3. Try ten pointer acquisitions, ten clicks, five drag releases, and three
   scrolls in each direction. Adjust **Closed pinch** or
   **Open pinch** if the engine misses your pinch or its release.
   Increase the drag threshold if short clicks turn into drags. To restore
   defaults, select **Restore defaults**, then
   **Save calibration**.
4. During separate drags, hold up an open palm, move out of view, or press
   **Esc** while the Studio has focus. In the palm trial, open all four
   fingers in one motion. Check that the button releases and the session
   pauses. Holding a fist afterward should leave the session paused.
5. After a successful simulation, grant Accessibility permission and select
   **Scan to control the Mac**. Hold your
   index finger still until **Pointer active** appears.
   Repeat the trials on the primary display with a scratch document and
   disposable draggable items. Keep the physical mouse available. Record
   failures by gesture and lighting level.
6. Close the Studio during a drag. Check that the mouse button releases and
   the camera light goes out. When you reopen the Studio, the session should
   start stopped.

The camera at index 0 is OpenCV's default. Stop the camera before choosing
another index. The mirrored preview works with either hand. On macOS,
the calibration file lives at
`~/Library/Application Support/KineticDesk/profile.json`. Set
`KINETICDESK_CONFIG_DIR` to use a different directory for testing.
