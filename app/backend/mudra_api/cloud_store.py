"""Cloud copies of the signer's **track points** in the team's Supabase project (teammate's ``database_isl`` studio).

Only numbers are stored: the hand and body landmarks of each tracked frame, in the studio's
``{t, pose, lh, rh, face}`` frame format, as a row in table ``signline_skeleton_recordings``
(``movement_sequence`` JSON). No video, no camera image, no audio is accepted by this module: a request carrying a
file is rejected, and there is no code path to the Storage bucket. Landmarks cannot be turned back into a face.

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
import time
from dataclasses import dataclass

import requests
from fastapi import APIRouter, Form, HTTPException, Request
from starlette.datastructures import UploadFile

from mudra_api.google_auth import session_user

log = logging.getLogger("mudra_api.cloud")
PURPOSES = ("learning", "communication", "custom_gesture")
TABLE = "signline_skeleton_recordings"
MAX_SKELETON_BYTES = 50 * 1024 * 1024
TIMEOUT_S = 90
# the studio's default signer (its tables reference Supabase auth users; app visitors are not Supabase users)
DEFAULT_USER_ID = "b69c50d6-f794-4129-ae8b-f96af77d98f2"
STORES = "track points only (hand and body landmarks); no video, images or audio"


@dataclass(frozen=True)
class CloudConfig:
    url: str
    key: str
    user_id: str

    @classmethod
    def from_env(cls) -> CloudConfig | None:
        url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
        key = os.getenv("SUPABASE_SECRET_KEY", "").strip()
        if not url or not key:
            return None
        return cls(url, key, os.getenv("SUPABASE_DEFAULT_USER_ID", "").strip() or DEFAULT_USER_ID)

    def headers(self, **extra: str) -> dict[str, str]:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}", **extra}


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
        out = {"configured": cfg is not None, "stores": STORES, "stores_video": False, "table": TABLE,
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
        """Store one recording's track points; returns the stored row's id and frame count."""
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
        try:
            row = insert_row(cfg, TABLE, {
                "user_id": cfg.user_id, "action_label": label, "purpose": purpose, "fps": round(seq_fps, 2),
                "frame_count": len(frames), "duration_seconds": round(seconds, 2),
                "movement_sequence": {"fps": seq_fps, "total_frames": len(frames), "duration_seconds": round(seconds, 2),
                                      "frames": frames},
                "metadata": {"source": "SignLine app", "tracker": "mediapipe-tasks hand + pose (no face mesh)",
                             "width": width, "height": height, "notes": notes[:500],
                             "signer_hash": signer_hash(user.get("email")), "zero_video_storage": True},
                "status": "completed",
            })
        except CloudError as exc:
            log.warning("Cloud save failed: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc)) from None
        except requests.RequestException as exc:
            log.warning("Cloud save failed: %s", type(exc).__name__)
            raise HTTPException(status_code=502, detail=f"Supabase is not reachable ({type(exc).__name__}).") from None
        log.info("Cloud save: %s %r %d frames", purpose, label, len(frames))
        return {"purpose": purpose, "label": label, "skeleton": {"id": row.get("id"), "frames": len(frames)}}

    return router
