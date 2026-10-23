"""A watchable video drawn from track points alone (cloud copies, docs/CLOUD_STORAGE.md).

Input: the studio's skeleton frames ``{t, pose, lh, rh, face}`` (numbers only; this is all the server ever receives,
see ``cloud_store.py``). Output: a WebM (VP8, VP9 as fallback) showing a stick figure on a dark background in the
SignLine Studio's style: cyan body, emerald left hand, violet right hand. No camera image exists anywhere in this
path, so the result cannot contain a face: ``draw_frame`` only ever paints the background and the palette colours
(checked by a test), and the encoder gets those drawings.

Frames are placed on a constant frame rate by their times (a point is held until the next one), so a 6 fps phone
recording still plays at normal speed. Long sessions are drawn smaller so a 5-minute Communication session renders
in seconds. Rendering uses OpenCV only (already a dependency).
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

import cv2
import numpy as np

BACKGROUND = (10, 5, 3)  # BGR of the studio's #03050a
BODY = (255, 255, 0)  # cyan
LEFT_HAND = (129, 185, 16)  # emerald #10b981
RIGHT_HAND = (246, 92, 139)  # violet #8b5cf6
CAPTION = (230, 230, 230)
PALETTE = {BACKGROUND, BODY, LEFT_HAND, RIGHT_HAND, CAPTION}

HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4), (0, 5), (5, 6), (6, 7), (7, 8), (0, 9), (9, 10), (10, 11), (11, 12),
    (0, 13), (13, 14), (14, 15), (15, 16), (0, 17), (17, 18), (18, 19), (19, 20), (5, 9), (9, 13), (13, 17),
]
# upper body as the app draws it: shoulders, arms, torso
POSE_CONNECTIONS = [(11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24)]
POSE_POINTS = (11, 12, 13, 14, 15, 16, 23, 24)
MIN_VISIBILITY = 0.5
DEFAULT_FPS = 25.0
MAX_SECONDS = 20 * 60
LONG_CLIP_S = 90.0  # longer clips are drawn at 480x360 and 15 fps (a 5-minute session renders in ~10 s)
LONG_CLIP_FPS = 15.0


class RenderError(Exception):
    pass


@dataclass(frozen=True)
class RenderInfo:
    width: int
    height: int
    fps: float
    frames: int
    codec: str
    size_bytes: int


def _point(p: dict, width: int, height: int) -> tuple[int, int] | None:
    x, y = p.get("x"), p.get("y")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    if not (-0.2 <= x <= 1.2 and -0.2 <= y <= 1.2):
        return None
    return round(x * width), round(y * height)


def _draw_hand(img: np.ndarray, pts: list | None, colour, width: int, height: int) -> None:
    if not isinstance(pts, list) or len(pts) < 21:
        return
    xy = [_point(p, width, height) if isinstance(p, dict) else None for p in pts[:21]]
    for a, b in HAND_CONNECTIONS:
        if xy[a] and xy[b]:
            cv2.line(img, xy[a], xy[b], colour, 2, cv2.LINE_8)
    for i, q in enumerate(xy):
        if q:
            cv2.circle(img, q, 4 if i in (4, 8, 12, 16, 20) else 3, colour, -1, cv2.LINE_8)


def _draw_body(img: np.ndarray, pose: list | None, width: int, height: int) -> None:
    if not isinstance(pose, list) or len(pose) < 25:
        return
    xy = {}
    for i in POSE_POINTS:
        p = pose[i]
        if isinstance(p, dict) and float(p.get("v", 1) or 0) >= MIN_VISIBILITY:
            xy[i] = _point(p, width, height)
    for a, b in POSE_CONNECTIONS:
        if xy.get(a) and xy.get(b):
            cv2.line(img, xy[a], xy[b], BODY, 3, cv2.LINE_8)
    for q in xy.values():
        if q:
            cv2.circle(img, q, 5, BODY, -1, cv2.LINE_8)


def draw_frame(frame: dict, width: int, height: int, caption: str = "") -> np.ndarray:
    """One picture of one skeleton frame: background plus palette colours only (no anti-aliasing, so a test can check)."""
    img = np.empty((height, width, 3), np.uint8)
    img[:] = BACKGROUND
    _draw_body(img, frame.get("pose"), width, height)
    _draw_hand(img, frame.get("lh"), LEFT_HAND, width, height)
    _draw_hand(img, frame.get("rh"), RIGHT_HAND, width, height)
    if caption:
        # text through a mask, so the letters are exactly the caption colour (OpenCV blends glyph edges otherwise)
        mask = np.zeros((height, width), np.uint8)
        cv2.putText(mask, caption[:60], (12, height - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.5, 255, 1, cv2.LINE_8)
        img[mask > 127] = CAPTION
    return img


def frame_times(frames: list) -> np.ndarray:
    t = np.array([float(f.get("t", 0) or 0) for f in frames], dtype=np.float64) / 1000.0
    return np.maximum.accumulate(t - t[0]) if len(t) else t


def output_size(width: int, height: int, seconds: float) -> tuple[int, int]:
    w, h = (int(width), int(height)) if width > 0 and height > 0 else (640, 480)
    scale = min(1.0, 1280 / w, 720 / h)
    if seconds > LONG_CLIP_S:
        scale = min(scale, 480 / w, 360 / h)
    w, h = max(160, int(w * scale) // 2 * 2), max(120, int(h * scale) // 2 * 2)
    return w, h


def render_skeleton_video(frames: list, width: int = 640, height: int = 480, fps: float = DEFAULT_FPS,
                          caption: str = "") -> tuple[bytes, RenderInfo]:
    """WebM bytes of the skeleton animation, plus what was rendered. Raises RenderError when no encoder works."""
    if not frames:
        raise RenderError("no frames")
    t = frame_times(frames)
    seconds = float(min(t[-1], MAX_SECONDS)) if len(t) > 1 else 1.0 / fps
    w, h = output_size(width, height, seconds)
    if seconds > LONG_CLIP_S:
        fps = min(fps, LONG_CLIP_FPS)
    n_out = max(2, round(seconds * fps) + 1)
    grid = np.arange(n_out) / fps
    idx = np.clip(np.searchsorted(t, grid, side="right") - 1, 0, len(frames) - 1)  # hold the latest frame
    last_err = None
    for fourcc, codec in (("VP80", "vp8"), ("VP90", "vp9")):
        fd, path = tempfile.mkstemp(suffix=".webm")
        os.close(fd)
        try:
            writer = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*fourcc), fps, (w, h))
            if not writer.isOpened():
                last_err = f"{codec}: writer did not open"
                continue
            cache: dict[int, np.ndarray] = {}
            for i in idx:
                i = int(i)
                if i not in cache:
                    cache = {i: draw_frame(frames[i], w, h, caption)}  # one picture per source frame, drawn once
                writer.write(cache[i])
            writer.release()
            with open(path, "rb") as fh:
                data = fh.read()
            if len(data) > 100:
                return data, RenderInfo(w, h, fps, n_out, codec, len(data))
            last_err = f"{codec}: empty file"
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
    raise RenderError(last_err or "no WebM encoder available")
