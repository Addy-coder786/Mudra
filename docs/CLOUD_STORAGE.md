# Cloud copies of track points (Supabase)

Added 2026-10-23 at the owner's request, and reduced the same day to **track points only** for the security
review: what people record in the app is also stored in the team's Supabase project, the one the teammate's
**SignLine Studio** (`boradesanidhya-ship-i/database_isl`) writes to, so its train-from-skeletons script sees the
app's recordings too. Nothing about recognition changed; a failed upload never affects the local save, and the
feature is off unless the server has the keys.

## Security summary (for the review)

| | |
|---|---|
| **Stored** | numbers only: 33 body points and 21 points per hand for each tracked frame (`x, y, z` in picture coordinates, body points with a visibility `v`), with the frame time, the word label, the purpose, duration and fps |
| **Never stored** | video, camera images, audio, face mesh points, the person's name or email |
| **Who signed** | when a Google account is signed in, only a 16-character one-way hash of the email (`metadata.signer_hash`), so one person's recordings can be grouped; no hash without sign-in |
| **Can a face be recovered?** | no: landmarks are a stick figure (positions of joints), not pixels |
| **Keys** | `SUPABASE_URL` and `SUPABASE_SECRET_KEY` live in the server's `.env` only; the browser never receives them and talks only to our backend |
| **Server guarantees** | `POST /cloud/recordings` accepts form fields only; a request carrying any file is rejected (422) before anything is sent; frames may contain only `t, pose, lh, rh, face` with numeric fields; the module has no code path to the Storage bucket |
| **Checkable** | `GET /cloud/status` → `"stores": "track points only (hand and body landmarks); no video, images or audio"`, `"stores_video": false` |
| **Consent** | the **Cloud save (track points only)** switch next to every camera control; off = nothing leaves the device; the Record page, the sign-in page and the legal pages say what is stored |

## What is stored, where

| | Teach a sign (`custom_gesture`) | Communication (`communication`) | Learning practice camera (`learning`) |
|---|---|---|---|
| When | each take, right after the local save (also when that save fails) | one upload per camera session, when the camera is stopped | one upload per practice session, when the camera is stopped |
| Label | the word being taught | the sentence shown (or "Communication session"); the recognised words in `notes` | the word / letter / phrase practised |

One row per recording in `signline_skeleton_recordings`, the studio's own format: `action_label`, `purpose`, `fps`,
`frame_count`, `duration_seconds`, `movement_sequence = {fps, total_frames, duration_seconds, frames}` with frames
`{t, pose[33]{x,y,z,v}, lh[21]{x,y,z}, rh[21]{x,y,z}, face: null}` (`lh` / `rh` = the signer's own left / right
hand), `metadata = {source, tracker, width, height, notes, signer_hash, zero_video_storage: true}`, `status:
completed`. Rows use the studio's default `user_id` (`SUPABASE_DEFAULT_USER_ID`): app visitors are not Supabase
users. Long sessions keep their first 9,000 frames (about 5 minutes). The studio's `signline_videos` table and the
`sign_line_video` bucket are not written by the app.

## How it works

- Browser: `services/cloudRecorder.js` (`CloudRecorder`: the track points of one session, built from the same tracker
  results the page already draws; `uploadRecording`: one form POST) and `features/cloud/useCloudRecorder.js`
  (`begin` / `frame` / `finish` / `cancel` for a page). The camera stream itself is never touched.
- Server: `mudra_api/cloud_store.py`: `GET /cloud/status` (`?check=1` adds a live row count), `POST /cloud/recordings`
  (fields `purpose`, `label`, `skeleton` JSON, `duration`, `fps`, `notes`, `width`, `height`), inserting through
  PostgREST with the secret key.
- Tests: `app/backend/tests/test_cloud_store.py` (10, Supabase stubbed: format, no personal data, files rejected,
  non-numeric frames rejected), `app/frontend/src/services/__tests__/cloudRecorder*.test.js` (4).

## Checked on 2026-10-23 (real Supabase project)

Track-points-only version, fake webcam: see HANDOVER Section 21 (row counts before / after, bucket unchanged).
Earlier the same day, before the change, a video version was checked and its test files and rows were deleted.

## Limits

- The studio's own tracker also stores face points; the app sends `face: null` on purpose.
- Row Level Security on the studio's table is bypassed by the secret key; rows belong to the default user.
- The studio's bucket still holds its own test videos; the app no longer needs the bucket at all.
