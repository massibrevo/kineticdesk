# Benchmarks and evaluation

Run the synthetic benchmark from the repository root.

```sh
.venv/bin/python scripts/benchmark.py --replay tests/fixtures/
```

On the Apple M3 Pro development Mac, 100 replays processed 14,500 frames.
Landmark geometry and gesture-state processing took 6.83 µs at the median and
8.33 µs at the 95th percentile. Each replay produced 39 position updates, one
click, one press-and-release pair, and eight scroll events. These measurements
cover the gesture engine. Camera capture, MediaPipe inference, UI rendering,
and OS event delivery fall outside the benchmark.

For webcam evaluation, repeat a fixed set of center and edge targets with each
hand under two lighting conditions. Record target error in logical pixels,
tracking availability, intended and recognized gestures, successful drags, and
false activations during ten minutes of idle testing. Use the marked trials to
calculate precision, recall, and clicks per minute. Report results separately
for each camera resolution and lighting condition.

The Studio reports median and 95th-percentile time from the completion of an
OpenCV frame read to the posting of an OS event. Measuring the delay from
physical movement to visible response requires an independent timing test.
Human accuracy and end-to-end response time are still unmeasured.
