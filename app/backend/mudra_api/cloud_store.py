"""Cloud copies of the signer's **track points** in the team's Supabase project (teammate's ``database_isl`` studio).

Only numbers arrive here: the hand and body landmarks of each tracked frame, in the studio's
``{t, pose, lh, rh, face}`` frame format, stored as a row in table ``signline_skeleton_recordings``
(``movement_sequence`` JSON). No camera video, image or audio is accepted: a request carrying a file is rejected.
From those numbers the server then **draws** a skeleton video (``skeleton_video.py``: stick figure on a dark
background) and stores it in the studio's bucket with a ``signline_videos`` row, so the recording can be watched in
the studio; the only pixels that ever exist are that drawing. Landmarks cannot be turned back into a face.

``purpose`` is one of ``learning`` (practice camera), ``communication`` (a Communication session) or
``custom_gesture`` (Teach a sign). The secret key stays on this server: the browser posts to ``/cloud/recordings``
and this module talks to Supabase (PostgREST over HTTPS with ``requests``). Nothing here is used for recognition;
a failed upload never affects the local save. Off unless ``SUPABASE_URL`` and ``SUPABASE_SECRET_KEY`` are set.

Who signed: when a Google user is signed in, only a short one-way hash of the email goes into the row's metadata
(``signer_hash``), so one person's recordings can be grouped for training without storing the address or name.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
from dataclasses import dataclass

import requests
from fastapi import APIRouter, Form, HTTPException, Request
from starlette.datastructures import UploadFile

from mudra_api.google_auth import session_user
from mudra_api.skeleton_video import RenderError, render_skeleton_video

log = logging.getLogger("mudra_api.cloud")
PURPOSES = ("learning", "communication", "custom_gesture")
TABLE = "signline_skeleton_recordings"
VIDEO_TABLE = "signline_videos"
MAX_SKELETON_BYTES = 50 * 1024 * 1024
TIMEOUT_S = 90
# the studio's default signer (its tables reference Supabase auth users; app visitors are not Supabase users)
DEFAULT_USER_ID = "b69c50d6-f794-4129-ae8b-f96af77d98f2"
STORES = ("track points (hand and body landmarks) and a skeleton video drawn from them; "
          "no camera video, images or audio")


@dataclass(frozen=True)
class CloudConfig:
    url: str
    key: str
    user_id: str
    bucket: str = "sign_line_video"
    skeleton_video: bool = True  # also store the drawn video (SUPABASE_SKELETON_VIDEO=off to keep rows only)

    @classmethod
    def from_env(cls) -> CloudConfig | None:
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
        if not url or not key:
            return None
        return cls(url, key, os.getenv("SUPABASE_DEFAULT_USER_ID", "").strip() or DEFAULT_USER_ID,
                   os.getenv("SUPABASE_BUCKET", "").strip() or "sign_line_video",
                   os.getenv("SUPABASE_SKELETON_VIDEO", "on").strip().lower() not in {"off", "0", "false", "no"})

    def headers(self, **extra: str) -> dict[str, str]:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", **extra}

    def public_url(self, path: str) -> str:
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{path}"


class CloudError(Exception):
    pass


def insert_row(cfg: CloudConfig, table: str, payload: dict) -> dict:
    headers = cfg.headers(**{"Content-Type": "application/json", "Prefer": "return=representation"})
    try:
        r = requests.post(f"{cfg.url}/rest/v1/{table}", timeout=TIMEOUT_S, json=payload, headers=headers)
    except requests.ConnectionError:  # a dropped connection (seen live, 2026-10-23): one more try
        time.sleep(1.0)
        r = requests.post(f"{cfg.url}/rest/v1/{table}", timeout=TIMEOUT_S, json=payload, headers=headers)
    if r.status_code >= 300:
        raise CloudError(f"{table} insert failed ({r.status_code}): {r.text[:200]}")
    body = r.json()
    return body[0] if isinstance(body, list) and body else body


def patch_row(cfg: CloudConfig, table: str, row_id: str, payload: dict) -> None:
    r = requests.patch(f"{cfg.url}/rest/v1/{table}?id=eq.{row_id}", timeout=TIMEOUT_S, json=payload,
                       headers=cfg.headers(**{"Content-Type": "application/json"}))
    if r.status_code >= 300:
        raise CloudError(f"{table} update failed ({r.status_code}): {r.text[:200]}")


def upload_object(cfg: CloudConfig, path: str, data: bytes, mime: str) -> None:
    """A file the server made itself (the skeleton drawing) into the bucket; browsers never reach this."""
    r = requests.post(f"{cfg.url}/storage/v1/object/{cfg.bucket}/{path}", data=data, timeout=TIMEOUT_S,
                      headers=cfg.headers(**{"Content-Type": mime, "x-upsert": "true"}))
    if r.status_code >= 300:
        raise CloudError(f"storage upload failed ({r.status_code}): {r.text[:200]}")


def remove_object(cfg: CloudConfig, path: str) -> None:
    try:
        requests.delete(f"{cfg.url}/storage/v1/object/{cfg.bucket}", timeout=TIMEOUT_S,
                        headers=cfg.headers(**{"Content-Type": "application/json"}), json={"prefixes": [path]})
    except requests.RequestException:  # best effort after a failed row insert
        pass


def store_skeleton_video(cfg: CloudConfig, frames: list, *, purpose: str, label: str, width: int, height: int,
                         seconds: float, skeleton_id, user_hash) -> dict:
    """Draw the video from the frames, put it in the bucket and in ``signline_videos``; returns what was stored."""
    started = time.perf_counter()
    data, info = render_skeleton_video(frames, width, height, caption=f"{label} · {purpose} · SignLine track points")
    path = f"videos/{purpose}/{int(time.time() * 1000)}_{secrets.token_hex(4)}_skeleton.webm"
    upload_object(cfg, path, data, "video/webm")
    try:
        row = insert_row(cfg, VIDEO_TABLE, {
            "user_id": cfg.user_id, "purpose": purpose, "detected_label": label, "storage_path": path,
            "mime_type": "video/webm", "size_bytes": len(data), "status": "uploaded",
            "result_json": {"rendered_from_skeleton": True, "zero_camera_video": True, "skeleton_recording_id": skeleton_id,
                            "uploaded_via": "SignLine app (skeleton render)", "public_url": cfg.public_url(path),
                            "duration_seconds": round(seconds, 2), "frames": info.frames, "fps": info.fps,
                            "width": info.width, "height": info.height, "codec": info.codec, "signer_hash": user_hash,
                            "render_ms": round((time.perf_counter() - started) * 1000)},
        })
    except CloudError:
        remove_object(cfg, path)
        raise
    return {"id": row.get("id"), "storage_path": path, "public_url": cfg.public_url(path), "size_bytes": len(data),
            "frames": info.frames, "fps": info.fps, "width": info.width, "height": info.height}


def count_rows(cfg: CloudConfig, table: str) -> int | None:
    r = requests.get(f"{cfg.url}/rest/v1/{table}?select=id", timeout=30,
                     headers=cfg.headers(**{"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"}))
    if r.status_code >= 300:
        return None
    rng = r.headers.get("Content-Range", "")
    return int(rng.rsplit("/", 1)[-1]) if "/" in rng and rng.rsplit("/", 1)[-1].isdigit() else None


def signer_hash(email: str | None) -> str | None:
    """A short one-way id of a signed-in person (grouping only; the address itself is never stored)."""
    if not email:
        return None
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()[:16]


def validate_skeleton(skeleton_json: str) -> tuple[list, float]:
    """The studio's frames list (``{t, pose, lh, rh, face}``) and its fps, from the browser's JSON; numbers only."""
    if len(skeleton_json) > MAX_SKELETON_BYTES:
        raise HTTPException(status_code=413, detail="The track points are too large.")
    try:
        data = json.loads(skeleton_json)
    except ValueError:
        raise HTTPException(status_code=422, detail="The track points are not valid JSON.") from None
    frames = data.get("frames") if isinstance(data, dict) else data
    if not isinstance(frames, list) or not frames:
        raise HTTPException(status_code=422, detail="The track points need a non-empty list of frames.")
    for f in frames:
        if not isinstance(f, dict) or not isinstance(f.get("t"), (int, float)):
            raise HTTPException(status_code=422, detail="Each frame needs a time t and landmark lists.")
        if set(f) - {"t", "pose", "lh", "rh", "face"}:
            raise HTTPException(status_code=422, detail="Frames may only carry t, pose, lh, rh and face.")
        for key in ("pose", "lh", "rh"):
            pts = f.get(key)
            if pts is not None and not (isinstance(pts, list) and all(isinstance(p, dict) and all(isinstance(v, (int, float)) for v in p.values()) for p in pts)):
                raise HTTPException(status_code=422, detail=f"{key} must be a list of points with numeric fields.")
    fps = float(data.get("fps", 0) or 0) if isinstance(data, dict) else 0.0
    return frames, fps


def cloud_router(config_factory=CloudConfig.from_env) -> APIRouter:
    router = APIRouter(prefix="/cloud", tags=["cloud storage"])

    @router.get("/status")
    def status(check: bool = False) -> dict:
        """Whether cloud copies are on (keys present) and what they contain; with ``check=1`` a live row count."""
        cfg = config_factory()
        out = {"configured": cfg is not None, "stores": STORES, "stores_video": False, "stores_camera_video": False,
               "stores_skeleton_video": bool(cfg and cfg.skeleton_video), "table": TABLE, "video_table": VIDEO_TABLE,
               "purposes": list(PURPOSES)}
        if cfg and check:
            try:
                out["rows"] = count_rows(cfg, TABLE)
                out["reachable"] = True
            except requests.RequestException as exc:
                out["reachable"] = False
                out["error"] = type(exc).__name__
        return out

    @router.post("/recordings", status_code=201)
    async def save_recording(request: Request, purpose: str = Form(...), label: str = Form(...),
                             skeleton: str = Form(...), duration: float = Form(0.0), fps: float = Form(0.0),
                             notes: str = Form(""), width: int = Form(0), height: int = Form(0)) -> dict:
        """Store one recording's track points, then the skeleton video drawn from them; returns what was stored."""
        cfg = config_factory()
        if cfg is None:
            raise HTTPException(status_code=503, detail="Cloud storage is not configured on this server.")
        form = await request.form()
        if any(isinstance(v, UploadFile) for v in form.values()):
            raise HTTPException(status_code=422, detail="Files are not accepted: only track points are stored, never video.")
        if purpose not in PURPOSES:
            raise HTTPException(status_code=422, detail=f"purpose must be one of {', '.join(PURPOSES)}.")
        label = label.strip()[:120] or "Sign Gesture"
        frames, frames_fps = validate_skeleton(skeleton)
        seq_fps = fps or frames_fps or 30.0
        seconds = float(duration) if duration else round(float(frames[-1]["t"]) / 1000, 2)
        user = session_user(request) or {}
        user_hash = signer_hash(user.get("email"))
        try:
            row = insert_row(cfg, TABLE, {
                "user_id": cfg.user_id, "action_label": label, "purpose": purpose, "fps": round(seq_fps, 2),
                "frame_count": len(frames), "duration_seconds": round(seconds, 2),
                "movement_sequence": {"fps": seq_fps, "total_frames": len(frames), "duration_seconds": round(seconds, 2),
                                      "frames": frames},
                "metadata": {"source": "SignLine app", "tracker": "mediapipe-tasks hand + pose (no face mesh)",
                             "width": width, "height": height, "notes": notes[:500],
                             "signer_hash": user_hash, "zero_video_storage": True, "camera_video": False},
                "status": "completed",
            })
        except CloudError as exc:
            log.warning("Cloud save failed: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from None
        except requests.RequestException as exc:
            log.warning("Cloud save failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail=f"Supabase is not reachable ({type(exc).__name__}).") from None
        result = {"purpose": purpose, "label": label, "skeleton": {"id": row.get("id"), "frames": len(frames)}, "video": None}
        if cfg.skeleton_video:  # the drawing is secondary: the track points are stored whatever happens here
            try:
                video = store_skeleton_video(cfg, frames, purpose=purpose, label=label, width=width, height=height,
                                             seconds=seconds, skeleton_id=row.get("id"), user_hash=user_hash)
                result["video"] = video
                if row.get("id"):
                    try:
                        patch_row(cfg, TABLE, row["id"], {"metadata": {**row.get("metadata", {}), "skeleton_video_path": video["storage_path"],
                                                                       "skeleton_video_id": video["id"]}})
                    except (CloudError, requests.RequestException) as exc:
                        log.warning("Cloud save: could not link the video to the track points: %s", type(exc).__name__)
            except (RenderError, CloudError, requests.RequestException) as exc:
                log.warning("Cloud save: skeleton video not stored: %s %s", type(exc).__name__, exc)
                result["video_error"] = f"{type(exc).__name__}: {exc}"[:200]
        log.info("Cloud save: %s %r %d frames, video %s", purpose, label, len(frames), "yes" if result["video"] else "no")
        return result

    return router
