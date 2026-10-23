"""Cloud copies of track points + the skeleton video drawn from them (mudra_api/cloud_store.py), Supabase stubbed."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mudra_api import cloud_store
from mudra_api.cloud_store import CloudConfig, cloud_router, signer_hash
from mudra_api.skeleton_video import RenderError, RenderInfo


class FakeResponse:
    def __init__(self, status_code=200, body=None, headers=None, text=""):
        self.status_code, self._body, self.headers, self.text = status_code, body, headers or {}, text

    def json(self):
        return self._body


STUB_WEBM = b"\x1a\x45\xdf\xa3WEBM-STUB"


@pytest.fixture
def fake(monkeypatch):
    """Records every Supabase call; `state` switches failures on. The renderer is a stub (its own tests cover it)."""
    calls = []
    state = {"fail_table": None, "fail_render": False}

    def post(url, **kw):
        calls.append(("POST", url, kw))
        if "/storage/v1/object/" in url:
            return FakeResponse(200, {"Key": url.rsplit("/", 1)[-1]})
        table = url.rsplit("/", 1)[-1]
        if state["fail_table"] == table:
            return FakeResponse(400, text="relation does not exist")
        return FakeResponse(201, [{"id": f"{table}-id", **kw["json"]}])

    def patch(url, **kw):
        calls.append(("PATCH", url, kw))
        return FakeResponse(204, [])

    def delete(url, **kw):
        calls.append(("DELETE", url, kw))
        return FakeResponse(200, [])

    def get(url, **kw):
        calls.append(("GET", url, kw))
        return FakeResponse(206, [], {"Content-Range": "0-0/7"})

    def render(frames, width, height, fps=25.0, caption=""):
        if state["fail_render"]:
            raise RenderError("no encoder")
        return STUB_WEBM, RenderInfo(width or 640, height or 480, fps, len(frames), "vp8", len(STUB_WEBM))

    monkeypatch.setattr(cloud_store.requests, "post", post)
    monkeypatch.setattr(cloud_store.requests, "patch", patch)
    monkeypatch.setattr(cloud_store.requests, "delete", delete)
    monkeypatch.setattr(cloud_store.requests, "get", get)
    monkeypatch.setattr(cloud_store, "render_skeleton_video", render)
    return calls, state


CFG = CloudConfig("https://x.supabase.co", "secret-key", "user-1")
CFG_ROWS_ONLY = CloudConfig("https://x.supabase.co", "secret-key", "user-1", skeleton_video=False)
FRAMES = {"fps": 25, "frames": [{"t": 0, "pose": None, "lh": [{"x": 0.1, "y": 0.2, "z": 0}] * 21, "rh": None, "face": None},
                                {"t": 40, "pose": [{"x": 0.5, "y": 0.4, "z": 0, "v": 0.99}] * 33, "lh": None, "rh": None, "face": None}]}


def client_for(cfg):
    app = FastAPI()
    app.include_router(cloud_router(lambda: cfg))
    return TestClient(app)


def test_status_says_what_is_stored_and_refuses_without_keys(fake):
    c = client_for(None)
    s = c.get("/cloud/status").json()
    assert s["configured"] is False and s["stores_camera_video"] is False and s["stores_video"] is False
    assert "no camera video" in s["stores"] and "skeleton video" in s["stores"]
    assert c.post("/cloud/recordings", data={"purpose": "learning", "label": "HELLO", "skeleton": json.dumps(FRAMES)}).status_code == 503
    s = client_for(CFG).get("/cloud/status?check=1").json()
    assert s["configured"] and s["stores_skeleton_video"] is True and s["table"] == "signline_skeleton_recordings" and s["rows"] == 7
    assert client_for(CFG_ROWS_ONLY).get("/cloud/status").json()["stores_skeleton_video"] is False


def test_track_points_then_the_drawn_video_are_stored_like_the_studio(fake, monkeypatch):
    calls, _ = fake
    monkeypatch.setattr(cloud_store, "session_user", lambda request: {"email": "Asha@Example.com", "name": "Asha", "role": "user"})
    c = client_for(CFG)
    r = c.post("/cloud/recordings", data={"purpose": "custom_gesture", "label": " Namaste ", "duration": "3.2", "fps": "25",
                                          "notes": "n", "width": "640", "height": "480", "skeleton": json.dumps(FRAMES)})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["skeleton"] == {"id": "signline_skeleton_recordings-id", "frames": 2}
    assert body["video"]["storage_path"].startswith("videos/custom_gesture/") and body["video"]["storage_path"].endswith("_skeleton.webm")
    assert body["video"]["public_url"] == f"https://x.supabase.co/storage/v1/object/public/sign_line_video/{body['video']['storage_path']}"
    assert body["video"]["size_bytes"] == len(STUB_WEBM) and body["video"]["frames"] == 2

    skeleton, upload, video, link = calls
    assert skeleton[1].endswith("/rest/v1/signline_skeleton_recordings")
    row = skeleton[2]["json"]
    assert row["action_label"] == "Namaste" and row["purpose"] == "custom_gesture" and row["user_id"] == "user-1"
    assert row["frame_count"] == 2 and row["fps"] == 25.0 and row["duration_seconds"] == 3.2
    assert row["movement_sequence"]["frames"] == FRAMES["frames"]
    assert row["metadata"]["zero_video_storage"] is True and row["metadata"]["camera_video"] is False
    assert row["metadata"]["signer_hash"] == signer_hash("asha@example.com")
    assert upload[1] == f"https://x.supabase.co/storage/v1/object/sign_line_video/{body['video']['storage_path']}"
    assert upload[2]["data"] == STUB_WEBM and upload[2]["headers"]["Content-Type"] == "video/webm"  # the drawing, never a browser file
    assert video[1].endswith("/rest/v1/signline_videos")
    vrow = video[2]["json"]
    assert vrow["purpose"] == "custom_gesture" and vrow["detected_label"] == "Namaste" and vrow["mime_type"] == "video/webm"
    assert vrow["status"] == "uploaded" and vrow["size_bytes"] == len(STUB_WEBM) and vrow["storage_path"] == body["video"]["storage_path"]
    assert vrow["result_json"]["rendered_from_skeleton"] is True and vrow["result_json"]["zero_camera_video"] is True
    assert vrow["result_json"]["skeleton_recording_id"] == "signline_skeleton_recordings-id"
    assert link[0] == "PATCH" and link[1].endswith("signline_skeleton_recordings?id=eq.signline_skeleton_recordings-id")
    assert link[2]["json"]["metadata"]["skeleton_video_path"] == body["video"]["storage_path"]
    whole = json.dumps([c[2].get("json") for c in calls]).lower()
    assert "asha" not in whole and "email" not in whole


def test_rows_only_mode_draws_nothing(fake):
    calls, _ = fake
    r = client_for(CFG_ROWS_ONLY).post("/cloud/recordings", data={"purpose": "learning", "label": "x", "skeleton": json.dumps(FRAMES)})
    assert r.status_code == 201 and r.json()["video"] is None and "video_error" not in r.json()
    assert [c[0] for c in calls] == ["POST"] and "storage" not in calls[0][1]


def test_a_failed_drawing_or_video_row_keeps_the_track_points(fake):
    calls, state = fake
    state["fail_render"] = True
    r = client_for(CFG).post("/cloud/recordings", data={"purpose": "learning", "label": "x", "skeleton": json.dumps(FRAMES)})
    assert r.status_code == 201 and r.json()["skeleton"]["frames"] == 2 and r.json()["video"] is None
    assert r.json()["video_error"].startswith("RenderError") and len(calls) == 1
    calls.clear()
    state["fail_render"] = False
    state["fail_table"] = "signline_videos"
    r = client_for(CFG).post("/cloud/recordings", data={"purpose": "learning", "label": "x", "skeleton": json.dumps(FRAMES)})
    assert r.status_code == 201 and r.json()["video"] is None and "insert failed" in r.json()["video_error"]
    removed = [c for c in calls if c[0] == "DELETE"]
    assert len(removed) == 1 and removed[0][2]["json"]["prefixes"][0].endswith("_skeleton.webm")


def test_files_from_the_browser_are_rejected_and_nothing_is_sent(fake):
    calls, _ = fake
    r = client_for(CFG).post("/cloud/recordings", data={"purpose": "learning", "label": "HELLO", "skeleton": json.dumps(FRAMES)},
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


def test_failed_track_point_insert_is_reported(fake):
    _, state = fake
    state["fail_table"] = "signline_skeleton_recordings"
    r = client_for(CFG).post("/cloud/recordings", data={"purpose": "communication", "label": "I need water", "skeleton": json.dumps(FRAMES["frames"])})
    assert r.status_code == 502 and "insert failed" in r.json()["detail"]


def test_signer_hash_is_stable_short_and_absent_without_a_signer():
    assert signer_hash("A@b.c") == signer_hash(" a@B.C ") and len(signer_hash("a@b.c")) == 16
    assert signer_hash(None) is None and signer_hash("") is None
    assert "a@b.c" not in signer_hash("a@b.c")
