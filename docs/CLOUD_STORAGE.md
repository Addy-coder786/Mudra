# Cloud copies of recordings (Supabase)

Added 2026-10-23 at the owner's request: what people record in the app is also stored in the team's Supabase
project, the one the teammate's **SignLine Studio** (`boradesanidhya-ship-i/database_isl`) writes to, so its sync and
retrain scripts see the app's recordings too. Nothing about recognition changed; a failed upload never affects the
local save, and the feature is off unless the server has the keys.

## What is stored, where

| | Teach a sign (`custom_gesture`) | Communication (`communication`) | Learning practice camera (`learning`) |
|---|---|---|---|
| When | each take, right after the local save (also when that save fails) | one upload per camera session, when the camera is stopped | one upload per practice session, when the camera is stopped |
| Label | the word being taught | the sentence shown (or "Communication session"); the recognised words in `notes` | the word / letter / phrase practised |

Two things go up for each recording, in the studio's own formats:

1. **The video**: the camera picture recorded in the browser (`MediaRecorder`, WebM, no sound) → Storage bucket
   `SUPABASE_BUCKET` (`sign_line_video`) at `videos/<purpose>/<timestamp>_<random>.webm`, plus a row in table
   `signline_videos` (`purpose`, `detected_label`, `storage_path`, `mime_type`, `size_bytes`, `status: uploaded`,
   `result_json` with duration, notes, picture size, the Google signer if signed in).
2. **The track points**: the hand and body landmarks of every tracked frame, the studio's
   `{t, pose[33]{x,y,z,v}, lh[21]{x,y,z}, rh[21]{x,y,z}, face: null}` frames → a row in
   `signline_skeleton_recordings` (`action_label`, `purpose`, `fps`, `frame_count`, `duration_seconds`,
   `movement_sequence.frames`, `metadata` with the video's storage path). `lh` / `rh` are the signer's own left /
   right hand. Long sessions keep their first 9,000 frames (about 5 minutes).

Both rows use the studio's default `user_id` (`SUPABASE_DEFAULT_USER_ID`): app visitors are not Supabase users.

## The switch and what people see

Every camera page shows **Cloud save: on / off / recording / uploading / saved / failed** next to the camera
controls (`components/CloudSaveBadge.jsx`); one tap turns it off, remembered in the browser
(`signline_cloud_save`). When the server has no keys it reads "Cloud save: not set up" and nothing leaves the
device. The Record page's notice and the legal pages say what is stored.

## How it works

- Browser: `services/cloudRecorder.js` (`CloudRecorder`: video + track points of one session; `uploadRecording`:
  one multipart POST) and `features/cloud/useCloudRecorder.js` (`begin` / `frame` / `finish` / `cancel` for a page).
- Server: `mudra_api/cloud_store.py`: `GET /cloud/status` (`?check=1` adds live row counts), `POST /cloud/recordings`
  (fields `purpose`, `label`, `duration`, `fps`, `notes`, `width`, `height`, `skeleton` JSON, file `video`). It
  uploads with the Storage REST API and inserts rows with PostgREST, using the **secret key from the server's
  environment only** (`SUPABASE_URL`, `SUPABASE_SECRET_KEY`, `SUPABASE_BUCKET`; `.env`, never in Git or the browser).
  A failed row insert removes the uploaded file again.
- Tests: `app/backend/tests/test_cloud_store.py` (5, Supabase stubbed), `app/frontend/src/services/__tests__/cloudRecorder*.test.js` (5).

## Checked on 2026-10-23 (real Supabase project)

Teach a sign with the fake webcam: local take saved, then `POST /cloud/recordings` → 201 with the video
(549 KB, `videos/custom_gesture/…webm`) and 74 frames of track points; the studio's counts went
`signline_videos` 7 → 8, `signline_skeleton_recordings` 4 → 5. The upload took about 2 s.
Communication: a 9 s session with the fake webcam, stopped with the Stop Camera button → 201 with the video (1.2 MB)
and 95 frames, label "Afternoon" (the recognised sentence). The test rows and files were deleted afterwards.
The bucket is public: a stored video can be opened by anyone who has its link (HTTP 200 on the `public_url`).
The Learning practice camera uses the same hook and was checked by its unit tests only.

## Limits and open points

- Videos show the person's face and room, and the bucket is public (links are unguessable but not protected). The switch is on by default because the owner asked for it; the pages say
  so. Turn it off (or leave the server keys unset) for anyone who has not agreed.
- The studio's own tracker also stores face points; the app sends `face: null` (it has no face mesh in the
  recording path).
- Row Level Security on the studio's tables is bypassed by the secret key; the rows belong to the default user.
- A long Communication session uploads one video of the whole session (the video is not cut per sign).
