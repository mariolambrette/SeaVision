"""Diagnostic: compare sequential reads with seek-based reads."""

import cv2
import numpy as np
import sys

path = sys.argv[1]

# --- Pure sequential (what the pipeline does) ---
cap_seq = cv2.VideoCapture(path)
sequential_frames = []
for i in range(150):
    ret, frame = cap_seq.read()
    if not ret:
        break
    sequential_frames.append(frame.copy())
cap_seq.release()

# --- SeekableVideoSource pattern (open, disturb, seek back) ---
cap_seek = cv2.VideoCapture(path)

# Simulate _check_initial_seek_accuracy
cap_seek.set(cv2.CAP_PROP_POS_FRAMES, 0)
cap_seek.read()  # This is the disturbance

# Now seek back to 0 and read sequentially (what the GUI does)
cap_seek.set(cv2.CAP_PROP_POS_FRAMES, 0)
seeked_frames = []
for i in range(150):
    ret, frame = cap_seek.read()
    if not ret:
        break
    seeked_frames.append(frame.copy())
cap_seek.release()

# --- Compare ---
print(f"Sequential frames: {len(sequential_frames)}")
print(f"Seek-based frames: {len(seeked_frames)}")
print()

for i in range(min(len(sequential_frames), len(seeked_frames))):
    match = np.array_equal(sequential_frames[i], seeked_frames[i])
    if not match:
        diff = np.abs(
            sequential_frames[i].astype(int) - seeked_frames[i].astype(int)
        ).mean()
        print(f"Frame {i:3d}: MISMATCH  (mean pixel diff: {diff:.1f})")
    else:
        print(f"Frame {i:3d}: identical")