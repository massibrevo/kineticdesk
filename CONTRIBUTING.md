# Contributing

Follow the setup and verification steps in the [README](README.md). When
reporting a gesture bug, describe the intended gesture, the expected result,
what happened, and any relevant timing. Use synthetic landmarks to reproduce
it when possible. Keep camera recordings, personal calibration profiles,
and generated model files out of commits.

Changes to gesture handling should preserve deterministic replay and emit
each button transition exactly once. Use synthetic replay or a simulated
input adapter in tests. Discuss new methods for sending desktop input and
their permission requirements before implementing them.
