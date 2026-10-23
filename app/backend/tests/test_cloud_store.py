"""Cloud copies of track points (mudra_api/cloud_store.py) with Supabase replaced by a fake HTTP layer."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mudra_api import cloud_store
from mudra_api.cloud_store import CloudConfig, cloud_router, signer_hash


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None, text=""):
        self.status_code, self._body, self.headers, self.text = status_code, body, headers or {}, text

    def json(self):
        return self._body


@pytest.fixture
def fake(monkeypatch):
    """Records every Supabase call; `fail` makes the insert fail."""
    calls = []
    state = {"fail": False}

    def post(url, **kw):
        calls.append(("POST", url, kw))
        if state["fail"]:
            return FakeResponse(400, text="relation does not exist")
        return FakeResponse(201, [{"id": "row-1", **kw["json"]}])

    def get(url, **kw):
        calls.append(("GET", url, kw))
        return FakeResponse(206, [], {"Content-Range": "0-0/7"})

    monkeypatch.setattr(cloud_store.requests, "post", post)
    monkeypatch.setattr(cloud_store.requests, "get", get)
    return calls, state


CFG = CloudConfig("https://x.supabase.co", "secret-key", "user-1")
FRAMES = {"fps": 25, "frames": [{"t": 0, "pose": None, "lh": [{"x": 0.1, "y": 0.2, "z": 0}] * 21, "rh": None, "face": None},
                                {"t": 40, "pose": [{"x": 0.5, "y": 0.4, "z": 0, "v": 0.99}] * 33, "lh": None, "rh": None, "face": None}]}


def client_for(cfg):
    app = FastAPI()
    app.include_router(cloud_router(lambda: cfg))
    return TestClient(app)


def test_status_says_what_is_stored_and_refuses_without_keys(fake):
    c = client_for(None)
    s = c.get("/cloud/status").json()
    assert s["configured"] is False and s["stores_video"] is False and "no video" in s["stores"]
    assert c.post("/cloud/recordings", data={"purpose": "learning", "label": "HELLO", "skeleton": json.dumps(FRAMES)}).status_code == 503
    c = client_for(CFG)
    s = c.get("/cloud/status?check=1").json()
    assert s["configured"] and s["table"] == "signline_skeleton_recordings" and s["rows"] == 7


def test_track_points_are_stored_like_the_studio_with_no_personal_data(fake, monkeypatch):
    calls, _ = fake
    monkeypatch.setattr(cloud_store, "session_user", lambda request: {"email": "Asha@Example.com", "name": "Asha", "role": "user"})
    c = client_for(CFG)
    r = c.post("/cloud/recordings", data={"purpose": "custom_gesture", "label": " Namaste ", "duration": "3.2", "fps": "25",
                                          "notes": "n", "width": "640", "height": "480", "skeleton": json.dumps(FRAMES)})
    assert r.status_code == 201, r.text
    assert r.json() == {"purpose": "custom_gesture", "label": "Namaste", "skeleton": {"id": "row-1", "frames": 2}}
    (_method, url, kw), = calls
    assert url == "https://x.supabase.co/rest/v1/signline_skeleton_recordings"
    assert kw["headers"]["Authorization"] == "Bearer secret-key" and kw["headers"]["Prefer"] == "return=representation"
    row = kw["json"]
    assert row["action_label"] == "Namaste" and row["purpose"] == "custom_gesture" and row["user_id"] == "user-1"
    assert row["frame_count"] == 2 and row["fps"] == 25.0 and row["duration_seconds"] == 3.2
    assert row["movement_sequence"]["frames"] == FRAMES["frames"]
    meta = row["metadata"]
    assert meta["zero_video_storage"] is True and meta["signer_hash"] == signer_hash("asha@example.com")
    assert "email" not in json.dumps(row).lower() and "asha" not in json.dumps(row).lower()
    assert all("storage" not in c[1] for c in calls)  # no Storage bucket call at all


def test_files_are_rejected_and_nothing_is_sent(fake):
    calls, _ = fake
    c = client_for(CFG)
    r = c.post("/cloud/recordings", data={"purpose": "learning", "label": "HELLO", "skeleton": json.dumps(FRAMES)},
               files={"video": ("take.webm", b"\x1a\x45webm-bytes", "video/webm")})
    assert r.status_code == 422 and "never video" in r.json()["detail"]
    assert calls == []


@pytest.mark.parametrize("skeleton,why", [
    ("not json", "not valid JSON"),
    ("[]", "non-empty"),
    (json.dumps([{"pose": None}]), "time t"),
    (json.dumps([{"t": 0, "image": "data:..."}]), "only carry"),
    (json.dumps([{"t": 0, "lh": [{"x": "0.1"}]}]), "numeric"),
])
def test_only_numeric_landmark_frames_are_accepted(fake, skeleton, why):
    calls, _ = fake
    c = client_for(CFG)
    r = c.post("/cloud/recordings", data={"purpose": "learning", "label": "x", "skeleton": skeleton})
    assert r.status_code == 422 and why in r.json()["detail"]
    assert calls == []
    assert c.post("/cloud/recordings", data={"purpose": "other", "label": "x", "skeleton": json.dumps(FRAMES)}).status_code == 422


def test_failed_insert_is_reported(fake):
    _, state = fake
    state["fail"] = True
    c = client_for(CFG)
    r = c.post("/cloud/recordings", data={"purpose": "communication", "label": "I need water", "skeleton": json.dumps(FRAMES["frames"])})
    assert r.status_code == 502 and "insert failed" in r.json()["detail"]


def test_signer_hash_is_stable_short_and_absent_without_a_signer():
    assert signer_hash("A@b.c") == signer_hash(" a@B.C ") and len(signer_hash("a@b.c")) == 16
    assert signer_hash(None) is None and signer_hash("") is None
    assert "a@b.c" not in signer_hash("a@b.c")
