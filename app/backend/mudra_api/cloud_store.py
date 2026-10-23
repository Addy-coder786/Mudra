"""Cloud copies of the signer's recordings in the team's Supabase project (teammate's ``database_isl`` studio).

What is stored, and where, follows that studio so its sync / retrain scripts keep working:

- the recorded **video** (WebM from the browser's MediaRecorder) in the Storage bucket ``SUPABASE_BUCKET`` at
  ``videos/<purpose>/<timestamp>_<random>.webm`` with a row in table ``signline_videos``;
- the **track points** (hand and body landmarks per frame, the studio's ``{t, pose, lh, rh, face}`` frames) as a row
  in table ``signline_skeleton_recordings`` (``movement_sequence`` JSON).

``purpose`` is one of ``learning`` (practice camera), ``communication`` (a Communication session) or
``custom_gesture`` (Teach a sign). The secret key stays on this server: the browser posts to ``/cloud/recordings``
and this module talks to Supabase (Storage and PostgREST over HTTPS with ``requests``). Nothing here is used for
recognition; a failed upload never affects the local save. Off unless ``SUPABASE_URL`` and ``SUPABASE_SECRET_KEY``
are set (``.env``).
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
from dataclasses import dataclass

import requests
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from mudra_api.google_auth import session_user

log = logging.getLogger("mudra_api.cloud")
PURPOSES = ("learning", "communication", "custom_gesture")
MAX_VIDEO_BYTES = 150 * 1024 * 1024
MAX_SKELETON_BYTES = 50 * 1024 * 1024
TIMEOUT_S = 90
# the studio's default signer (its tables reference Supabase auth users; app visitors are not Supabase users)
DEFAULT_USER_ID = "b69c50d6-f794-4129-ae8b-f96af77d98f2"
VIDEO_FILE = File(None)  # the optional multipart video field


@dataclass(frozen=True)
class CloudConfig:
    url: str
    key: str
    bucket: str
    user_id: str

    @classmethod
    def from_env(cls) -> CloudConfig | None:
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
        if not url or not key:
            return None
        return cls(url, key, os.getenv("SUPABASE_BUCKET", "sign_line_video").strip() or "sign_line_video",
                   os.getenv("SUPABASE_DEFAULT_USER_ID", "").strip() or DEFAULT_USER_ID)

    def headers(self, **extra: str) -> dict[str, str]:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", **extra}

    def public_url(self, path: str) -> str:
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{path}"


class CloudError(Exception):
    pass


def storage_path(purpose: str, ext: str = "webm") -> str:
    return f"videos/{purpose}/{int(time.time() * 1000)}_{secrets.token_hex(4)}.{ext}"


def upload_object(cfg: CloudConfig, path: str, data: bytes, mime: str) -> None:
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


def insert_row(cfg: CloudConfig, table: str, payload: dict) -> dict:
    r = requests.post(f"{cfg.url}/rest/v1/{table}", timeout=TIMEOUT_S, json=payload,
                      headers=cfg.headers(**{"Content-Type": "application/json", "Prefer": "return=representation"}))
    if r.status_code >= 300:
        raise CloudError(f"{table} insert failed ({r.status_code}): {r.text[:200]}")
    body = r.json()
    return body[0] if isinstance(body, list) and body else body


def count_rows(cfg: CloudConfig, table: str) -> int | None:
    r = requests.get(f"{cfg.url}/rest/v1/{table}?select=id", timeout=30,
                     headers=cfg.headers(**{"Prefer": "count=exact", "Range-Unit": "items", "Range": "0-0"}))
    if r.status_code >= 300:
        return None
    rng = r.headers.get("Content-Range", "")
    return int(rng.rsplit("/", 1)[-1]) if "/" in rng and rng.rsplit("/", 1)[-1].isdigit() else None


def validate_skeleton(skeleton_json: str) -> tuple[list, float]:
    """The studio's frames list (``{t, pose, lh, rh, face}``) and its fps, from the browser's JSON."""
    if len(skeleton_json) > MAX_SKELETON_BYTES:
        raise HTTPException(status_code=413, detail="The track points are too large.")
    try:
        data = json.loads(skeleton_json)
    except ValueError:
        raise HTTPException(status_code=422, detail="The track points are not valid JSON.") from None
    frames = data.get("frames") if isinstance(data, dict) else data
    if not isinstance(frames, list) or not frames or not all(isinstance(f, dict) and "t" in f for f in frames):
        raise HTTPException(status_code=422, detail="The track points need a non-empty list of frames with t.")
    fps = float(data.get("fps", 0) or 0) if isinstance(data, dict) else 0.0
    return frames, fps


def cloud_router(config_factory=CloudConfig.from_env) -> APIRouter:
    router = APIRouter(prefix="/cloud", tags=["cloud storage"])

    @router.get("/status")
    def status(check: bool = False) -> dict:
        """Whether cloud copies are on (keys present); with ``check=1`` also a live count from the tables."""
        cfg = config_factory()
        out = {"configured": cfg is not None, "bucket": cfg.bucket if cfg else None, "purposes": list(PURPOSES)}
        if cfg and check:
            try:
                out["tables"] = {t: count_rows(cfg, t) for t in ("signline_videos", "signline_skeleton_recordings")}
                out["reachable"] = True
            except requests.RequestException as exc:
                out["reachable"] = False
                out["error"] = type(exc).__name__
        return out

    @router.post("/recordings", status_code=201)
    async def save_recording(request: Request, purpose: str = Form(...), label: str = Form(...),
                             duration: float = Form(0.0), fps: float = Form(0.0), notes: str = Form(""),
                             width: int = Form(0), height: int = Form(0), skeleton: str | None = Form(None),
                             video: UploadFile | None = VIDEO_FILE) -> dict:
        """Store one recording's video and / or track points; returns what was stored."""
        cfg = config_factory()
        if cfg is None:
            raise HTTPException(status_code=503, detail="Cloud storage is not configured on this server.")
        if purpose not in PURPOSES:
            raise HTTPException(status_code=422, detail=f"purpose must be one of {', '.join(PURPOSES)}.")
        label = label.strip()[:120] or "Sign Gesture"
        if video is None and skeleton is None:
            raise HTTPException(status_code=422, detail="Send a video, the track points, or both.")
        user = session_user(request) or {}
        signer = {"email": user.get("email"), "name": user.get("name"), "google": bool(user)}
        result: dict = {"purpose": purpose, "label": label}
        try:
            if video is not None:
                data = await video.read()
                if not data:
                    raise HTTPException(status_code=422, detail="The video is empty.")
                if len(data) > MAX_VIDEO_BYTES:
                    raise HTTPException(status_code=413, detail="The video is larger than 150 MB.")
                mime = video.content_type or "video/webm"
                path = storage_path(purpose, "mp4" if "mp4" in mime else "webm")
                upload_object(cfg, path, data, mime)
                try:
                    row = insert_row(cfg, "signline_videos", {
                        "user_id": cfg.user_id, "purpose": purpose, "detected_label": label, "storage_path": path,
                        "mime_type": mime, "size_bytes": len(data), "status": "uploaded",
                        "result_json": {"original_name": video.filename, "duration_seconds": duration, "notes": notes,
                                        "uploaded_via": "SignLine app", "public_url": cfg.public_url(path),
                                        "signer": signer, "width": width, "height": height},
                    })
                except CloudError:
                    remove_object(cfg, path)
                    raise
                result["video"] = {"id": row.get("id"), "storage_path": path, "public_url": cfg.public_url(path),
                                   "size_bytes": len(data)}
            if skeleton is not None:
                frames, frames_fps = validate_skeleton(skeleton)
                seq_fps = fps or frames_fps or 30.0
                seconds = duration or round(frames[-1]["t"] / 1000, 2) if isinstance(frames[-1].get("t"), (int, float)) else duration
                row = insert_row(cfg, "signline_skeleton_recordings", {
                    "user_id": cfg.user_id, "action_label": label, "purpose": purpose, "fps": round(seq_fps, 2),
                    "frame_count": len(frames), "duration_seconds": round(float(seconds), 2),
                    "movement_sequence": {"fps": seq_fps, "total_frames": len(frames),
                                          "duration_seconds": round(float(seconds), 2), "frames": frames},
                    "metadata": {"source": "SignLine app", "tracker": "mediapipe-tasks hand+pose (no face)",
                                 "width": width, "height": height, "signer": signer, "notes": notes,
                                 "video_storage_path": result.get("video", {}).get("storage_path"),
                                 "zero_video_storage": "video" not in result},
                    "status": "completed",
                })
                result["skeleton"] = {"id": row.get("id"), "frames": len(frames)}
        except CloudError as exc:
            log.warning("Cloud save failed: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from None
        except requests.RequestException as exc:
            log.warning("Cloud save failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail=f"Supabase is not reachable ({type(exc).__name__}).") from None
        log.info("Cloud save: %s %r video=%s skeleton=%s", purpose, label, "video" in result, "skeleton" in result)
        return result

    return router
