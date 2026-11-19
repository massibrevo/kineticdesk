# Benchmark and evaluation

Run `.venv/bin/python scripts/benchmark.py --replay tests/fixtures/`. On the
Apple M3 Pro development Mac, 100 deterministic replays exercised 14,500 frames.
A local run recorded 6.08 µs median and 7.29 µs p95 for landmark geometry and
gesture-state processing. Each replay emitted 38 position updates, one short
click, one down/up pair and six scroll events. Camera acquisition, MediaPipe
inference, the browser, and OS dispatch are outside this measurement.

For live evaluation, repeat a fixed set of center and edge targets with each
hand and at two lighting levels. Record endpoint error in logical pixels,
tracking availability, intended and emitted gestures, successful drags, and
false activations during a ten-minute no-action period. Report precision,
recall and clicks per minute using the marked trials. The Studio’s median/p95
for desktop input time spans frame availability after OpenCV read through event
posting. Motion-to-visible-response timing needs an independent measurement.
Keep the timing and outcomes separate by camera resolution and lighting.

No human accuracy or end-to-end latency figures have been collected.
