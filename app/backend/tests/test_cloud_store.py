"""Cloud copies of recordings (mudra_api/cloud_store.py) with Supabase replaced by a fake HTTP layer."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mudra_api import cloud_store
from mudra_api.cloud_store import CloudConfig, cloud_router


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None, text=""):
        self.status_code, self._body, self.headers, self.text = status_code, body, headers or {}, text

    def json(self):
        return self._body


@pytest.fixture
def fake(monkeypatch):
    """Records every Supabase call; `fail` names the table whose insert fails."""
    calls = []
    state = {"fail": None}

    def post(url, **kw):
        calls.append(("POST", url, kw))
        if "/storage/v1/object/" in url:
            return FakeResponse(200, {"Key": url.rsplit("/", 1)[-1]})
        table = url.rsplit("/", 1)[-1]
        if state["fail"] == table:
            return FakeResponse(400, text="relation does not exist")
        return FakeResponse(201, [{"id": f"{table}-id-1", **kw["json"]}])

    def delete(url, **kw):
        calls.append(("DELETE", url, kw))
        return FakeResponse(200, [])

    def get(url, **kw):
        calls.append(("GET", url, kw))
        return FakeResponse(206, [], {"Content-Range": "0-0/7"})

    monkeypatch.setattr(cloud_store.requests, "post", post)
    monkeypatch.setattr(cloud_store.requests, "delete", delete)
    monkeypatch.setattr(cloud_store.requests, "get", get)
    return calls, state


CFG = CloudConfig("https://x.supabase.co", "secret-key", "sign_line_video", "user-1")
FRAMES = {"fps": 25, "frames": [{"t": 0, "pose": None, "lh": [{"x": 0.1, "y": 0.2, "z": 0}] * 21, "rh": None, "face": None},
                                {"t": 40, "pose": None, "lh": None, "rh": None, "face": None}]}


def client_for(cfg):
    app = FastAPI()
    app.include_router(cloud_router(lambda: cfg))
    return TestClient(app)


def test_status_and_refusal_when_not_configured(fake):
    c = client_for(None)
    assert c.get("/cloud/status").json()["configured"] is False
    r = c.post("/cloud/recordings", data={"purpose": "learning", "label": "HELLO", "skeleton": json.dumps(FRAMES)})
    assert r.status_code == 503
    c = client_for(CFG)
    s = c.get("/cloud/status?check=1").json()
    assert s["configured"] and s["bucket"] == "sign_line_video" and s["tables"]["signline_videos"] == 7


def test_video_and_track_points_are_stored_like_the_studio(fake):
    calls, _ = fake
    c = client_for(CFG)
    r = c.post("/cloud/recordings", data={"purpose": "custom_gesture", "label": " Namaste ", "duration": "3.2", "fps": "25",
                                          "notes": "n", "width": "640", "height": "480", "skeleton": json.dumps(FRAMES)},
               files={"video": ("take.webm", b"\x1a\x45webm-bytes", "video/webm")})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["video"]["storage_path"].startswith("videos/custom_gesture/") and body["video"]["storage_path"].endswith(".webm")
    assert body["video"]["public_url"] == f"https://x.supabase.co/storage/v1/object/public/sign_line_video/{body['video']['storage_path']}"
    assert body["skeleton"] == {"id": "signline_skeleton_recordings-id-1", "frames": 2}
    upload, videos, skeleton = calls
    assert upload[1] == f"https://x.supabase.co/storage/v1/object/sign_line_video/{body['video']['storage_path']}"
    assert upload[2]["headers"]["Authorization"] == "Bearer secret-key" and upload[2]["headers"]["x-upsert"] == "true"
    assert upload[2]["data"] == b"\x1a\x45webm-bytes"
    row = videos[2]["json"]
    assert videos[1].endswith("/rest/v1/signline_videos") and videos[2]["headers"]["Prefer"] == "return=representation"
    assert row["detected_label"] == "Namaste" and row["purpose"] == "custom_gesture" and row["user_id"] == "user-1"
    assert row["size_bytes"] == 12 and row["status"] == "uploaded" and row["result_json"]["duration_seconds"] == 3.2
    seq = skeleton[2]["json"]
    assert skeleton[1].endswith("/rest/v1/signline_skeleton_recordings")
    assert seq["action_label"] == "Namaste" and seq["frame_count"] == 2 and seq["fps"] == 25.0
    assert seq["movement_sequence"]["frames"] == FRAMES["frames"] and seq["duration_seconds"] == 3.2
    assert seq["metadata"]["video_storage_path"] == body["video"]["storage_path"] and seq["metadata"]["zero_video_storage"] is False


def test_track_points_only_and_bad_input(fake):
    c = client_for(CFG)
    r = c.post("/cloud/recordings", data={"purpose": "communication", "label": "I need water", "skeleton": json.dumps(FRAMES["frames"])})
    assert r.status_code == 201 and "video" not in r.json() and r.json()["skeleton"]["frames"] == 2
    assert c.post("/cloud/recordings", data={"purpose": "other", "label": "x", "skeleton": "[]"}).status_code == 422
    assert c.post("/cloud/recordings", data={"purpose": "learning", "label": "x"}).status_code == 422
    assert c.post("/cloud/recordings", data={"purpose": "learning", "label": "x", "skeleton": "not json"}).status_code == 422
    assert c.post("/cloud/recordings", data={"purpose": "learning", "label": "x", "skeleton": "[]"}).status_code == 422


def test_failed_row_insert_removes_the_uploaded_video(fake):
    calls, state = fake
    state["fail"] = "signline_videos"
    c = client_for(CFG)
    r = c.post("/cloud/recordings", data={"purpose": "learning", "label": "HELLO"},
               files={"video": ("take.webm", b"bytes", "video/webm")})
    assert r.status_code == 502 and "signline_videos insert failed" in r.json()["detail"]
    removed = [c for c in calls if c[0] == "DELETE"]
    assert len(removed) == 1 and removed[0][2]["json"]["prefixes"][0].startswith("videos/learning/")


def test_signer_from_the_google_session_goes_into_the_metadata(fake, monkeypatch):
    calls, _ = fake
    monkeypatch.setattr(cloud_store, "session_user", lambda request: {"email": "a@b.c", "name": "Asha", "role": "user"})
    c = client_for(CFG)
    r = c.post("/cloud/recordings", data={"purpose": "learning", "label": "HELLO", "skeleton": json.dumps(FRAMES)})
    assert r.status_code == 201
    assert calls[-1][2]["json"]["metadata"]["signer"] == {"email": "a@b.c", "name": "Asha", "google": True}
