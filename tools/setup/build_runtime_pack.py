"""Build data/runtime/: the landmark files the app itself reads, small enough for Git, so a fresh clone runs
Learning ("how to sign it" examples, the avatar), letters, phrases and the taught words on any PC.

    app/backend/.venv/Scripts/python.exe tools/setup/build_runtime_pack.py
    ... --exclude islwords,islsentences,letters,app     (leave out sources whose owners have not agreed)

Only numbers are packed (landmark points); every file's metadata is rewritten from a short allow-list, so no
local path, file name or person's name leaves this machine. App recordings get a neutral signer id.
The backend falls back to this folder when the full data/ is absent (mudra_api/settings.py) and copies the
app takes into data/ on first start (mudra_api/recordings.py: seed_recordings).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
from dataclasses import asdict, fields
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "app" / "backend"), str(ROOT / "training" / "src")]

from mudra_api.references import PREFERRED_SOURCES, ReferenceClips
from mudra_ml.data.manifest import ManifestRow, read_manifest

DATA = ROOT / "data"
OUT = DATA / "runtime"
WORD_SPLIT = DATA / "metadata" / "splits" / "combined_words_v3" / "train.csv"
PHRASE_SPLIT = DATA / "metadata" / "splits" / "phrases_v1" / "train.csv"
LETTERS = DATA / "processed" / "landmarks" / "letters"
WORLD = DATA / "processed" / "landmarks" / "reference_world"
APP_MANIFEST = DATA / "metadata" / "manifest_app.csv"
SEQUENCE_KEYS = ("hands", "hand_present", "hand_score", "pose", "pose_present", "timestamps_ms")
META_KEYS = ("label", "source", "sample_id", "kind", "fps", "source_fps", "decoded_frames", "width", "height",
             "schema_version", "extractor_version", "pose_model", "mirrored_input", "timestamps_are_frame_indices",
             "category", "signer")
SOURCE_NAMES = {
    "include": "INCLUDE pose release (AI4Bharat OpenHands, Zenodo 6674324, CC-BY-4.0)",
    "include_video": "INCLUDE original videos (Zenodo 4010759, CC-BY-4.0), re-extracted with MediaPipe",
    "islwords": "MUDRA team word recordings (licence to be confirmed)",
    "islsentences": "team sentence videos (licence to be confirmed)",
    "letters": "team alphabet photos (licence to be confirmed)",
    "app": "signs recorded in the app (Teach a sign) by the MUDRA team",
}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def pseudonyms(rows: list[ManifestRow]) -> dict[str, str]:
    """Recorder name -> signer-01, signer-02, ... (by first appearance); 'anonymous' stays as it is."""
    names: dict[str, str] = {}
    for r in rows:
        name = r.signer_id.split(":", 1)[-1]
        if name and name != "anonymous" and name not in names:
            names[name] = f"signer-{len(names) + 1:02d}"
    return names


def write_sequence(src: Path, dst: Path, signer: str | None = None) -> None:
    with np.load(src, allow_pickle=False) as z:
        arrays = {k: z[k] for k in SEQUENCE_KEYS}
        meta = json.loads(str(z["meta"]))
    meta = {k: meta[k] for k in META_KEYS if k in meta}
    if signer is not None:
        meta["signer"] = signer
    else:
        meta.pop("signer", None)
    dst.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(dst, **arrays, meta=np.array(json.dumps(meta)))


def pack_examples(split: Path, sources: tuple[str, ...], name: str) -> list[ManifestRow]:
    """The example ReferenceClips would show for each label, copied with clean metadata."""
    rows = []
    for _, r in sorted(ReferenceClips(split, sources=sources).best.values(), key=lambda b: b[1].label):
        dst = OUT / name / r.label / f"{r.sample_id}.npz"
        write_sequence(Path(r.landmarks_path), dst)
        rows.append(ManifestRow(**{**asdict(r), "raw_path": "", "landmarks_path": rel(dst), "signer_id": "",
                                   "group_id": f"{r.source}:clip:{r.sample_id}"}))
    return rows


def pack_app() -> list[ManifestRow]:
    rows = read_manifest(APP_MANIFEST)
    names = pseudonyms(rows)
    out = []
    for r in rows:
        src = Path(r.landmarks_path)
        if not src.exists():
            continue
        name = r.signer_id.split(":", 1)[-1]
        signer = names.get(name, name or "anonymous")
        dst = OUT / "app" / r.label / f"{r.sample_id}.npz"
        write_sequence(src, dst, signer)
        day = r.group_id.rsplit(":", 1)[-1] if r.group_id.count(":") >= 3 else ""
        out.append(ManifestRow(**{**asdict(r), "raw_path": rel(dst), "landmarks_path": rel(dst),
                                  "signer_id": f"app:{signer}",
                                  "group_id": f"app:session:{signer}" + (f":{day}" if day else "")}))
    return out


def pack_letters() -> int:
    n = 0
    for src in sorted(LETTERS.glob("*.npz")):
        with np.load(src, allow_pickle=False) as z:  # photo file names ("files") are left out
            arrays = {k: z[k] for k in ("hands", "present", "handedness", "score")}
        dst = OUT / "letters" / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(dst, **arrays)
        n += 1
    return n


def pack_world(labels: set[str], excluded: set[str]) -> dict[str, int]:
    """3D re-extractions (extract_reference_world.py) of the word examples; returns files per source video."""
    n: dict[str, int] = {}
    for src in sorted(WORLD.glob("*.npz")):
        if src.stem not in labels:
            continue
        with np.load(src, allow_pickle=False) as z:  # the video path ("source_path") is left out
            arrays = {k: z[k] for k in z.files if k != "source_path"}
            source = "include_video" if "include_video" in str(z["source_path"]) else "islwords"
        if source in excluded:
            continue
        dst = OUT / "reference_world" / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(dst, **arrays)
        n[source] = n.get(source, 0) + 1
    return n


def write_manifest(path: Path, rows: list[ManifestRow]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[fl.name for fl in fields(ManifestRow)], lineterminator="\n")
        w.writeheader()
        w.writerows(asdict(r) for r in rows)


def write_checksums() -> int:
    files = sorted(p for p in OUT.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(OUT).as_posix()}" for p in files]
    (OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")  # LF: sha256sum -c
    return len(files)


def write_readme(counts: dict[str, int], sources: dict[str, int], excluded: set[str]) -> None:
    src_lines = "\n".join(f"| `{s}` | {SOURCE_NAMES.get(s.split(' ')[0], s)} | {n} |" for s, n in sorted(sources.items()))
    left_out = ", ".join(sorted(excluded)) or "nothing"
    (OUT / "README.md").write_text(f"""# Runtime data pack

Generated by `tools/setup/build_runtime_pack.py`; do not edit by hand (rebuild instead). This is what the
app reads at run time, so a fresh clone works without the full `data/` folder: the "how to sign it" examples
and the avatar in Learning, fingerspelled letters, phrases, and the words taught on the Record page.

**Only landmark points** (numbers: hand, body and world joint positions per frame). No video, image or audio,
no local file path or file name, no person's name: app recordings carry a neutral signer id (`signer-01`).

| | Files |
|---|---|
| `words/` + `words.csv`: one example per word (the one the app shows) | {counts['words']} |
| `phrases/` + `phrases.csv`: one example per phrase | {counts['phrases']} |
| `reference_world/`: 3D re-extraction of word examples, for the avatar | {counts['world']} |
| `letters/`: hand shapes per letter (photo landmarks; file names removed) | {counts['letters']} |
| `app/` + `manifest_app.csv`: Teach-a-sign recordings; copied into `data/` on the first start | {counts['app']} |

Left out at build time: {left_out}.

## Sources and licences

| Source | Where it comes from | Files |
|---|---|---|
{src_lines}

INCLUDE: Sridhar, Ganesan, Kumar and Khapra, "INCLUDE: A Large Scale Dataset for Indian Sign Language
Recognition", ACM Multimedia 2020; licensed CC-BY-4.0 (attribution). Sources marked "licence to be confirmed"
are the team's own recordings: rebuild with `--exclude <source>` if an owner objects.

`SHA256SUMS` lists a checksum per file (`sha256sum -c SHA256SUMS` from this folder).
""", encoding="utf-8", newline="\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exclude", default="", help="comma-separated sources to leave out: "
                    "islwords, include_video, include, islsentences, letters, app")
    args = ap.parse_args()
    excluded = {s.strip() for s in args.exclude.split(",") if s.strip()}
    unknown = excluded - set(SOURCE_NAMES)
    if unknown:
        ap.error(f"unknown source(s): {', '.join(sorted(unknown))}")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    word_sources = tuple(s for s in PREFERRED_SOURCES if s not in excluded)
    words = pack_examples(WORD_SPLIT, word_sources, "words") if word_sources else []
    phrases = pack_examples(PHRASE_SPLIT, ("islsentences",), "phrases") if "islsentences" not in excluded else []
    app = pack_app() if "app" not in excluded and APP_MANIFEST.exists() else []
    write_manifest(OUT / "words.csv", words)
    write_manifest(OUT / "phrases.csv", phrases)
    write_manifest(OUT / "manifest_app.csv", app)
    letters = pack_letters() if "letters" not in excluded else 0
    world_by_source = pack_world({r.label for r in words}, excluded)
    world = sum(world_by_source.values())

    sources: dict[str, int] = {}
    for r in [*words, *phrases, *app]:
        sources[r.source] = sources.get(r.source, 0) + 1
    for source, n in world_by_source.items():
        sources[f"{source} (3D)"] = n
    if letters:
        sources["letters"] = letters
    counts = {"words": len(words), "phrases": len(phrases), "world": world, "letters": letters, "app": len(app)}
    write_readme(counts, sources, excluded)
    total = write_checksums()
    size = sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file())
    print(json.dumps({**counts, "files": total, "megabytes": round(size / 1e6, 1), "excluded": sorted(excluded)}))


if __name__ == "__main__":
    main()
