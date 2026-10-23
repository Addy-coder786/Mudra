# Cloud copies of track points, and the skeleton video drawn from them (Supabase)

Added 2026-10-23 at the owner's request, reduced the same day to **track points only** for the security
review, then given a **server-drawn skeleton video** so recordings can be watched in the studio: what people record in the app is also stored in the team's Supabase project, the one the teammate's
**SignLine Studio** (`boradesanidhya-ship-i/database_isl`) writes to, so its train-from-skeletons script sees the
app's recordings too. Nothing about recognition changed; a failed upload never affects the local save, and the
feature is off unless the server has the keys.

## Security summary (for the review)

| | |
|---|---|
| **Stored** | numbers: 33 body points and 21 points per hand for each tracked frame (`x, y, z` in picture coordinates, body points with a visibility `v`), with the frame time, the word label, the purpose, duration and fps; **plus a video the server draws from those numbers** (stick figure on a dark background, `mudra_api/skeleton_video.py`) so the recording can be watched |
| **Never stored** | camera video, camera images, audio, face mesh points, the person's name or email. The only pixels that exist anywhere are the server's drawing, made after the browser's numbers arrived |
| **Who signed** | when a Google account is signed in, only a 16-character one-way hash of the email (`metadata.signer_hash`), so one person's recordings can be grouped; no hash without sign-in |
| **Can a face be recovered?** | no: landmarks are a stick figure (positions of joints), not pixels |
| **Keys** | `SUPABASE_URL` and `SUPABASE_SECRET_KEY` live in the server's `.env` only; the browser never receives them and talks only to our backend |
| **Server guarantees** | `POST /cloud/recordings` accepts form fields only; a request carrying any file is rejected (422) before anything is sent; frames may contain only `t, pose, lh, rh, face` with numeric fields. The only file the server ever uploads is its own drawing (`store_skeleton_video`); `draw_frame` paints the background and four palette colours only (checked by `test_draw_frame_paints_only_the_palette_colours`: no photograph can be in it) |
| **Checkable** | `GET /cloud/status` → `"stores": "track points … and a skeleton video drawn from them; no camera video, images or audio"`, `"stores_camera_video": false`, `"stores_skeleton_video": true` |
| **Consent** | the **Cloud save (track points only)** switch next to every camera control; off = nothing leaves the device; the Record page, the sign-in page and the legal pages say what is stored |

## What is stored, where

| | Teach a sign (`custom_gesture`) | Communication (`communication`) | Learning practice camera (`learning`) |
|---|---|---|---|
| When | each take, right after the local save (also when that save fails) | one upload per camera session, when the camera is stopped | one upload per practice session, when the camera is stopped |
| Label | the word being taught | the sentence shown (or "Communication session"); the recognised words in `notes` | the word / letter / phrase practised |

**Track points:** one row per recording in `signline_skeleton_recordings`, the studio's own format: `action_label`, `purpose`, `fps`,
`frame_count`, `duration_seconds`, `movement_sequence = {fps, total_frames, duration_seconds, frames}` with frames
`{t, pose[33]{x,y,z,v}, lh[21]{x,y,z}, rh[21]{x,y,z}, face: null}` (`lh` / `rh` = the signer's own left / right
hand), `metadata = {source, tracker, width, height, notes, signer_hash, zero_video_storage: true}`, `status:
completed`. Rows use the studio's default `user_id` (`SUPABASE_DEFAULT_USER_ID`): app visitors are not Supabase
users. Long sessions keep their first 9,000 frames (about 5 minutes).

**Skeleton video:** after the row, the server draws the frames (cyan body, emerald left hand, violet right hand
on the studio's dark background; a caption with the label and purpose; constant 25 fps by holding each point
until the next one; 640×480, or 480×360 at 15 fps for clips over 90 s) and encodes a VP8 WebM with OpenCV. The
file goes to the bucket `SUPABASE_BUCKET` at `videos/<purpose>/<ts>_<rand>_skeleton.webm` with a row in
`signline_videos` (`detected_label`, `purpose`, `storage_path`, `mime_type: video/webm`, `size_bytes`, `status:
uploaded`, `result_json` with `rendered_from_skeleton: true`, `zero_camera_video: true`, `skeleton_recording_id`,
`public_url`, duration, frames, fps, size, codec, `signer_hash`, render time), and the skeleton row's metadata
gets `skeleton_video_path` / `skeleton_video_id`. The studio lists it like any video. The video is secondary: if
drawing or uploading fails, the track points stay stored and the response carries `video: null, video_error`.
`SUPABASE_SKELETON_VIDEO=off` keeps the rows only.

## How it works

- Browser: `services/cloudRecorder.js` (`CloudRecorder`: the track points of one session, built from the same tracker
  results the page already draws; `uploadRecording`: one form POST) and `features/cloud/useCloudRecorder.js`
  (`begin` / `frame` / `finish` / `cancel` for a page). The camera stream itself is never touched.
- Server: `mudra_api/cloud_store.py`: `GET /cloud/status` (`?check=1` adds a live row count), `POST /cloud/recordings`
  (fields `purpose`, `label`, `skeleton` JSON, `duration`, `fps`, `notes`, `width`, `height`), inserting through
  PostgREST with the secret key.
- Tests: `app/backend/tests/test_cloud_store.py` (12, Supabase and the renderer stubbed: format, no personal data,
  files rejected, non-numeric frames rejected, video row format, video failures keep the points, rows-only mode),
  `test_skeleton_video.py` (6: palette-only pixels, playable WebM with the right frame count and motion, slow-camera
  frames held to the grid, long clips smaller), `app/frontend/src/services/__tests__/cloudRecorder*.test.js` (4).

## Checked on 2026-10-23 (real Supabase project)

With the skeleton video, fake webcam: Teach a sign take → 65 frames of track points + a 2.9 s video (73 frames,
136 KB, 640×480); Communication 9 s session → 158 frames + a 7.0 s video (176 frames, 307 KB). Both videos opened
in Chrome from their public URLs (duration and size read back, a frame captured: stick figure, caption, dark
background). Render time: 0.4 s for a 3 s take; a 5-minute session renders in about 10 s at 480×360 / 15 fps.
Test rows and files were deleted afterwards. Earlier versions the same day (camera video; then rows only) were
checked the same way.

## Limits

- The studio's own tracker also stores face points; the app sends `face: null` on purpose.
- Row Level Security on the studio's tables is bypassed by the secret key; rows belong to the default user.
- The bucket is public: anyone with a link can open a skeleton video (a stick figure, no person visible).
- VP8 WebM plays in Chrome, Edge, Firefox and Android; iPhone Safari may not play it. An MP4 would need an H.264
  encoder on the server (OpenH264), which this machine does not have.
- For Sanidhya: the new `signline_videos` rows carry `rendered_from_skeleton: true`; his sync / retrain scripts
  treat every row as a camera video, so they should skip or knowingly use these.
