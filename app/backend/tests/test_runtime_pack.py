"""The committed runtime pack (data/runtime, tools/setup/build_runtime_pack.py): enough for a fresh clone, and
nothing personal in it."""

import csv
import json
import re
from pathlib import Path

import numpy as np
import pytest
from mudra_ml.data.manifest import read_manifest

from mudra_api.library import LetterReferences
from mudra_api.recordings import seed_recordings
from mudra_api.references import ReferenceClips
from mudra_api.settings import RUNTIME_DIR, Settings, _data_path

pytestmark = pytest.mark.skipif(not (RUNTIME_DIR / "words.csv").exists(), reason="runtime pack not built")
PERSONAL = re.compile(r"adnan|[a-z]:\\|users[\\/]|\.(mp4|mov|jpg|jpeg|png|pkl)\b", re.IGNORECASE)


def test_pack_has_no_names_paths_or_file_names():
    for path in RUNTIME_DIR.rglob("*"):
        if path.suffix in (".csv", ".md"):
            assert not PERSONAL.search(path.read_text(encoding="utf-8")), path
        elif path.suffix == ".npz":
            with np.load(path, allow_pickle=False) as z:
                assert "source_path" not in z.files and "files" not in z.files, path
                for k in z.files:
                    if z[k].dtype.kind in "US":
                        assert not PERSONAL.search(str(z[k])), (path, k)


def test_app_takes_carry_a_neutral_signer_id():
    with (RUNTIME_DIR / "manifest_app.csv").open(encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert rows and all(re.fullmatch(r"app:(signer-\d\d|anonymous)", r["signer_id"]) for r in rows)
    with np.load(RUNTIME_DIR / rows[0]["landmarks_path"].removeprefix("data/runtime/"), allow_pickle=False) as z:
        assert json.loads(str(z["meta"]))["signer"] == rows[0]["signer_id"].split(":", 1)[1]


def test_pack_alone_serves_examples_letters_and_phrases():
    words = ReferenceClips(RUNTIME_DIR / "words.csv", world_dir=RUNTIME_DIR / "reference_world")
    assert len(words.available) > 300
    clip = words.get(min(words.available))
    assert clip["frames"] and clip["fps"] > 0
    assert len(ReferenceClips(RUNTIME_DIR / "phrases.csv", sources=("islsentences",)).available) > 90
    assert len(LetterReferences(RUNTIME_DIR / "letters")._frames) == 26


def test_settings_use_the_pack_only_without_the_full_data(tmp_path, monkeypatch):
    packed = tmp_path / "packed.csv"
    packed.write_text("x")
    assert _data_path("MUDRA_TEST_PATH", tmp_path / "missing.csv", packed) == packed
    assert _data_path("MUDRA_TEST_PATH", tmp_path, packed) == tmp_path  # the full dataset wins when present
    monkeypatch.setenv("MUDRA_TEST_PATH", "elsewhere.csv")
    assert str(_data_path("MUDRA_TEST_PATH", tmp_path, packed)) == "elsewhere.csv"
    assert Settings().reference_split.exists()


def test_seed_copies_the_takes_once(tmp_path):
    n = seed_recordings(tmp_path, RUNTIME_DIR)
    manifest = tmp_path / "metadata" / "manifest_app.csv"
    assert n > 0 and manifest.exists()
    rows = read_manifest(manifest)
    assert len(rows) == n
    assert all(Path(r.landmarks_path).is_relative_to(tmp_path / "processed" / "landmarks" / "app")
               and Path(r.landmarks_path).exists() for r in rows)
    manifest.write_text(manifest.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    assert seed_recordings(tmp_path, RUNTIME_DIR) == 0  # an existing manifest (own recordings) is never replaced
    assert len(manifest.read_text(encoding="utf-8").splitlines()) == 1
