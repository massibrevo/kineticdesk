# KineticDesk

KineticDesk lets you control your Mac's pointer with one hand and a webcam.
It recognizes movement, clicks, drag and drop, scrolling, and pause. Video is
processed on your Mac. Start with the built-in demo or practice with the webcam
before enabling desktop control.

![KineticDesk Studio during a synthetic replay, showing tracked hand landmarks and the drag target](docs/studio-replay.png)

## Run the macOS app

If you already have `KineticDesk.app`, double-click it in Finder. The app includes
the Studio, the local service, and the hand-tracking model. macOS prompts for
Camera access when you first start a hand scan or a webcam simulation.

To build the app from source, run the bootstrap below, then run
`python3 scripts/build_macos.py`. The build produces
`.cache/macos/dist/KineticDesk.app` for your Mac's architecture.

For updates, reuse your own macOS signing identity with
`python3 scripts/build_macos.py --signing-identity "Developer ID Application: …"`.
macOS ties permissions for ad-hoc builds to the specific build. If the
Accessibility switch is already on but the updated app still reports missing
permission, quit KineticDesk, remove its old entry in **Privacy & Security**,
and authorize the installed copy again. Keep backup bundles outside Finder's
application list, for example in a ZIP archive.

## Run from source

You need macOS, Node.js 22, and [uv](https://docs.astral.sh/uv/). You can use
Python 3.11 or 3.12 in place of uv. From the repository root, run:

```sh
python3 scripts/bootstrap.py
python3 scripts/dev.py
```

Open the printed URL, usually `http://127.0.0.1:5173`. If that port is in use,
run `python3 scripts/dev.py --port 5174`. The bootstrap downloads the pinned
dependencies and the official MediaPipe model. The Studio runs offline after
setup.

## Try the gestures

The Studio opens in English. Use the **Language** selector to switch to
**Italiano**. KineticDesk saves your choice.

Choose **Gesture demo** to run a synthetic sequence or **Simulation only** to
practice with your webcam. Use **Show preview** to check the framing and
**Expand Studio** to enlarge the workspace. The default tracking area covers
80% of each frame dimension. A saved calibration overrides these defaults.

Select **Start scan and control the Mac**. If the native app needs Accessibility
permission on your first scan attempt, it opens the macOS permission pane once.
Enable KineticDesk, return to the app, and start the scan again. To reopen the
pane, select **Open Accessibility** in the Studio. When running from source,
grant permission to the launcher in **System Settings → Privacy & Security →
Accessibility**.

Show one hand and hold your index finger up until the progress bar fills.
When you see **Pointer active**, move your hand to steer the
pointer. Choose **Return to simulation** to practice
without sending input to macOS.

| Gesture | Action |
| --- | --- |
| Hold your index finger steady for about half a second during a scan | Enables desktop control. In simulation, hold a fist for 750 ms to start. |
| Extend your index finger with the other fingers relaxed | Moves the pointer. Relax your index finger to stop it. |
| Briefly pinch your thumb and index finger after pointing | Left-clicks on release. |
| Hold the pinch for about 400 ms | Grabs the item. Move your hand to drag, then open the pinch to drop. |
| Extend your index and middle fingers and move them vertically | Scrolls while keeping the pointer still. |
| Hold up an open palm | Pauses control. Start a new scan to resume. |

**Esc** pauses control while the Studio has focus. **Stop** also turns off the
camera. On macOS, close, hide, or minimize the Studio to keep an active desktop
session running in the background. Use **KD** in the menu bar to reopen the
Studio, pause control, stop the camera, or quit. The menu reports when desktop
control or the camera is active. A scan must finish before you close the window.

In a browser, hiding the Studio tab pauses control. Moving the physical pointer
into a corner of the main display triggers the fail-safe on the next input
action. Mac sleep, session changes, and app quit stop capture and release any held
button. Quit the native app with **⌘Q** or press **Ctrl+C** in the terminal if
you launched from source.

## Verification and platform support

```sh
python3 scripts/verify.py
.venv/bin/python scripts/benchmark.py --replay tests/fixtures/
```

For the browser tests, leave the Studio running on port 5174. In a second terminal,
run:

```sh
cd frontend
npx playwright install chromium
npx playwright test
```

Automated tests use synthetic replay or a simulated input adapter. On an Apple
Silicon Mac, manual checks covered the native app, live webcam capture,
permission detection, Quartz initialization, and MediaPipe inference. Live
gesture accuracy and actual pointer injection from the installed app still
need validation. Desktop control targets the primary display on macOS.

- [Architecture and model](docs/architecture.md)
- [Gesture state machine](docs/gesture-state-machine.md)
- [Calibration and webcam check](docs/calibration.md)
- [Privacy and security](docs/privacy-security.md)
- [Benchmarks and evaluation](docs/benchmarks.md)
- [Contributing](CONTRIBUTING.md)

The source code uses the [MIT License](LICENSE). The build downloads the
official model separately.
