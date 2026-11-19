# Synthetic landmark fixtures

The benchmark loads five manually constructed hand poses from
[replay_poses.json](../../backend/kineticdesk/replay_poses.json).
[replay.py](../../backend/kineticdesk/replay.py) interpolates between the poses
on a fixed timeline so each run receives the same inputs. The fixtures use
synthetic coordinates and contain no camera recordings.
