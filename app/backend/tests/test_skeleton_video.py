"""The skeleton video drawn from track points (mudra_api/skeleton_video.py): nothing but the palette can be in it."""

from __future__ import annotations

import os
import tempfile

import cv2
import numpy as np

from mudra_api.skeleton_video import (
    PALETTE,
    draw_frame,
    output_size,
    render_skeleton_video,
)


def _frames(n=30, step_ms=40):
    out = []
    for i in range(n):
        s = i / max(n - 1, 1)
        pose = [{"x": 0.5, "y": 0.9, "z": 0, "v": 1.0} for _ in range(33)]
        pose[11] = {"x": 0.62, "y": 0.4, "z": 0, "v": 0.99}
        pose[12] = {"x": 0.38, "y": 0.4, "z": 0, "v": 0.99}
        pose[13] = {"x": 0.7, "y": 0.6, "z": 0, "v": 0.9}
        pose[15] = {"x": 0.7 - 0.2 * s, "y": 0.5, "z": 0, "v": 0.9}
        pose[14] = {"x": 0.3, "y": 0.6, "z": 0, "v": 0.2}  # not visible: not drawn
        pose[23] = {"x": 0.6, "y": 0.85, "z": 0, "v": 1}
        pose[24] = {"x": 0.4, "y": 0.85, "z": 0, "v": 1}
        rh = [{"x": 0.7 - 0.2 * s + 0.004 * k, "y": 0.5 + 0.003 * k, "z": 0} for k in range(21)]
        out.append({"t": i * step_ms, "pose": pose, "lh": None, "rh": rh, "face": None})
    return out


def test_draw_frame_paints_only_the_palette_colours():
    img = draw_frame(_frames(1)[0], 640, 480, caption="Namaste · custom_gesture")
    assert img.shape == (480, 640, 3)
    colours = {tuple(int(c) for c in rgb) for rgb in np.unique(img.reshape(-1, 3), axis=0)}
    assert colours <= PALETTE, colours - PALETTE
    assert len(colours) >= 4  # background, body, hand, caption all present
    blank = draw_frame({"t": 0, "pose": None, "lh": None, "rh": None, "face": None}, 320, 240)
    assert {tuple(int(c) for c in rgb) for rgb in np.unique(blank.reshape(-1, 3), axis=0)} == {(10, 5, 3)}


def test_out_of_range_and_malformed_points_are_skipped():
    frame = {"t": 0, "pose": None, "lh": [{"x": 5, "y": 5, "z": 0}] * 21, "rh": [{"x": "a", "y": 0.5}] * 21, "face": None}
    img = draw_frame(frame, 320, 240)
    assert {tuple(int(c) for c in rgb) for rgb in np.unique(img.reshape(-1, 3), axis=0)} == {(10, 5, 3)}


def test_output_size_keeps_short_clips_and_shrinks_long_ones():
    assert output_size(640, 480, 10) == (640, 480)
    assert output_size(1280, 720, 10) == (1280, 720)
    assert output_size(1920, 1080, 10) == (1280, 720)
    assert output_size(640, 480, 300) == (480, 360)
    assert output_size(0, 0, 5) == (640, 480)


def test_render_gives_a_playable_webm_at_a_constant_frame_rate():
    frames = _frames(30, 40)  # 1.16 s at 25 fps
    data, info = render_skeleton_video(frames, 640, 480, fps=25, caption="Namaste · custom_gesture")
    assert data[:4] == b"\x1a\x45\xdf\xa3"  # EBML / WebM magic
    assert info.codec in ("vp8", "vp9") and info.width == 640 and info.height == 480 and info.frames == 30
    fd, path = tempfile.mkstemp(suffix=".webm")
    os.close(fd)
    try:
        with open(path, "wb") as fh:
            fh.write(data)
        cap = cv2.VideoCapture(path)
        assert cap.isOpened()
        n, moving = 0, False
        first = None
        while True:
            ok, img = cap.read()
            if not ok:
                break
            n += 1
            if first is None:
                first = img
            elif not moving and np.abs(img.astype(int) - first.astype(int)).max() > 60:
                moving = True
        cap.release()
    finally:
        os.remove(path)
    assert n == 30 and moving  # every grid frame is there and the hand moves across the clip


def test_slow_camera_frames_are_held_to_the_grid():
    frames = _frames(7, 200)  # 5 fps for 1.2 s
    data, info = render_skeleton_video(frames, 320, 240, fps=25)
    assert info.frames == 31 and len(data) > 100


def test_long_sessions_render_smaller_and_slower():
    frames = _frames(50, 2000)  # 98 s
    _, info = render_skeleton_video(frames, 640, 480, fps=25)
    assert (info.width, info.height, info.fps) == (480, 360, 15.0) and info.frames == 98 * 15 + 1
