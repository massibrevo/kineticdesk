# Calibration and camera smoke test

1. Select **Solo simulazione** to start the webcam in dry-run. Place it approximately at eye level and use
   diffuse lighting. Keep the other hand outside the frame.
2. Show a fist until the progress indicator completes. Point at the four edges
   of the tracking guide with a comfortable wrist position. If the full practice
   area is hard to reach, stop the source and edit the normalized bounds under
   **Calibrazione**. A narrower area maps less hand travel to the full output.
3. Test ten cursor acquisitions, ten taps, five drag releases and three scrolls
   in each direction. Stop and adjust **Pinza chiusa**, **Pinza aperta** and the
   drag threshold if clicks turn into drags. Use **Ripristina valori** followed
   by **Salva calibrazione** to return to defaults.
4. Start each trial while dragging. Open your palm, move out of camera view,
   or press Escape in separate trials. In the palm trial, open all four fingers without
   pausing in the pointing pose. Expect a release followed by pause. Show a fist
   again and check that the paused session stays paused.
5. Only after a successful dry-run, grant Accessibility and select **Scansiona
   per controllare il Mac**. Hold your extended index still until the progress
   bar fills and **Puntatore attivo** appears. Repeat the
   same trials on the main display using a local scratch document and harmless
   draggable UI. Keep the terminal and physical mouse available. Record failures
   by gesture and lighting instead of extrapolating from synthetic tests.
6. Close the Studio during a held drag. Verify that the mouse is released and
   the camera LED turns off. Relaunch the Studio and verify that it is stopped.

Camera index 0 is the OpenCV default. Other indices can be selected after stopping
the source. Mirroring works for either hand. The calibration file lives at
`~/Library/Application Support/KineticDesk/profile.json` on macOS. The environment
variable `KINETICDESK_CONFIG_DIR` overrides the directory for tests.
