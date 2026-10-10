"""Tests de disk_index (aucun reseau, uniquement tmp_path)."""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import disk_index  # noqa: E402
from disk_index import parse_filename, scan_profile_dir, ids_on_disk  # noqa: E402

ID1 = "7300000000000000001"
ID2 = "7300000000000000002"
ID3 = "7300000000000000003"


@pytest.mark.parametrize("name,expected", [
    (f"20240101_user_{ID1}.mp4", (ID1, "video")),
    (f"20240101_{ID1}.mp4", (ID1, "video")),
    (f"{ID1}.mp4", (ID1, "video")),
    (f"NA_{ID1}.mp4", (ID1, "video")),
    (f"NA_user_{ID1}.WEBM", (ID1, "video")),
    (f"20240101_my_user_name_{ID1}.mkv", (ID1, "video")),
    (f"20240101_my.user.name_{ID1}.mov", (ID1, "video")),
    (f"20240101_user_{ID1}_img=3.jpg", (ID1, "slideshow")),
    (f"20240101_a_b.c_{ID1}_img=12.PNG", (ID1, "slideshow")),
    (f"20240101_user_{ID1}_img=1.webp", (ID1, "slideshow")),
    (f"20240101_user_{ID1}.jpg", None),
    ("notes.txt", None),
    ("20240101_user_123.mp4", None),
    (f"20240101_user_{ID1}.mp4.part", None),
    (f"20240101_user_{ID1}.f137.mp4", None),
])
def test_parse_filename(name, expected):
    assert parse_filename(name) == expected


def touch(path, content=b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def test_scan_formats_and_slideshow(tmp_path):
    touch(tmp_path / f"20240101_us_er.x_{ID1}.mp4", b"abc")
    touch(tmp_path / f"20240101_user_{ID2}_img=1.jpg", b"aa")
    touch(tmp_path / f"20240101_user_{ID2}_img=2.jpg", b"bbb")
    res = scan_profile_dir(str(tmp_path))
    assert set(res) == {ID1, ID2}
    assert res[ID1].kind == "video" and res[ID1].size == 3
    assert res[ID2].kind == "slideshow"
    assert res[ID2].image_count == 2 and res[ID2].size == 5
    assert len(res[ID2].files) == 2
    assert res[ID2].mtime > 0
    assert ids_on_disk(str(tmp_path)) == {ID1, ID2}


def test_legacy_slideshow_folder(tmp_path):
    folder = tmp_path / f"20230101_user_{ID3}"
    touch(folder / "1.jpg")
    touch(folder / "2.png")
    touch(folder / "readme.txt")
    res = scan_profile_dir(str(tmp_path))
    assert res[ID3].kind == "slideshow"
    assert res[ID3].image_count == 2
    assert len(res[ID3].files) == 2


def test_ignored_files(tmp_path):
    user = tmp_path / "bob"
    for n in [f"20240101_bob_{ID1}.mp4.part", f"20240101_bob_{ID1}.mp4.tmp",
              f"20240101_bob_{ID1}.mp4.ytdl", f"20240101_bob_{ID1}.mp4.backup",
              f"20240101_bob_{ID1}.temp.mp4", f"20240101_bob_{ID1}.f137.mp4",
              f".20240101_bob_{ID1}.mp4", "scan_state.json", "link_state.json",
              "bob_videos.txt", f"{ID1}.json", f"20240101_bob_{ID1}.jpg"]:
        touch(user / n)
    touch(user / f"20240101_bob_{ID2}.mp4", b"")  # taille 0
    assert scan_profile_dir(str(user)) == {}


def test_empty_and_missing(tmp_path):
    assert scan_profile_dir(str(tmp_path)) == {}
    missing = tmp_path / "nope"
    assert scan_profile_dir(str(missing)) == {}
    assert not missing.exists()


def test_single_scandir_no_listdir_getsize(tmp_path, monkeypatch):
    touch(tmp_path / f"20240101_u_{ID1}.mp4")
    touch(tmp_path / f"20240101_u_{ID2}_img=1.jpg")

    def boom(*a, **k):
        raise AssertionError("appel interdit")
    monkeypatch.setattr(os, "listdir", boom)
    monkeypatch.setattr(os.path, "getsize", boom)
    calls = []
    real = os.scandir
    monkeypatch.setattr(os, "scandir", lambda p: (calls.append(p), real(p))[1])
    assert set(scan_profile_dir(str(tmp_path))) == {ID1, ID2}
    assert len(calls) == 1


def test_1000_files_fast(tmp_path):
    for i in range(1000):
        touch(tmp_path / f"20240101_user_{7300000000000000000 + i}.mp4")
    start = time.time()
    res = scan_profile_dir(str(tmp_path))
    assert len(res) == 1000
    assert time.time() - start < 2.0
