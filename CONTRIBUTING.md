# Contributing

Run the bootstrap and verification commands in the README. Reproduce gesture
issues using synthetic landmarks where possible. Describe the requested
gesture, expected state, observed state and timing. Keep camera recordings,
personal profiles and generated model assets out of commits.

Behavior changes to the gesture engine should preserve deterministic replay and
exactly-once button transitions. Tests must use the replay or a fake input
adapter. Discuss new OS injection methods and permissions before adding them.
