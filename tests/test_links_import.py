"""Tests unitaires de links_import (aucun accès réseau ni disque hors tmp_path)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import links_import  # noqa: E402
from links_import import parse_links  # noqa: E402


def U(user, vid, kind="video"):
    return f"https://www.tiktok.com/@{user}/{kind}/{vid}"


def test_basic_one_per_line_grouped_in_order():
    text = "\n".join([U("alice", 1), U("bob", 2), U("alice", 3, "photo")])
    groups, report = parse_links(text)
    assert list(groups) == ["alice", "bob"]
    assert [i["id"] for i in groups["alice"]] == ["1", "3"]
    assert groups["alice"][1]["url"] == U("alice", 3, "photo")
    assert report["total"] == 3 and report["ignored"] == 0 and report["invalid"] == []


def test_item_shape():
    groups, _ = parse_links(U("Alice", 42))
    assert groups == {"alice": [{"id": "42", "url": U("Alice", 42), "username": "Alice"}]}


def test_query_and_fragment_stripped():
    groups, _ = parse_links("https://www.tiktok.com/@alice/video/123?is_from_webapp=1&sender_device=pc#x")
    assert groups["alice"][0]["url"] == U("alice", 123)


def test_trailing_slash_and_no_www_and_mobile_host_and_http():
    text = "\n".join([
        "https://tiktok.com/@a/video/1/",
        "http://m.tiktok.com/@a/video/2",
        "www.tiktok.com/@a/video/3",
        "tiktok.com/@a/photo/4",
    ])
    groups, _ = parse_links(text)
    assert [i["url"] for i in groups["a"]] == [U("a", n, "photo" if n == 4 else "video") for n in (1, 2, 3, 4)]


def test_uppercase_host_and_type_normalized():
    groups, _ = parse_links("HTTPS://WWW.TIKTOK.COM/@Bob/VIDEO/77")
    assert groups["bob"][0]["url"] == U("Bob", 77)


@pytest.mark.parametrize("sep", [",", ";", " ", "\t", " | ", ",\n"])
def test_various_separators(sep):
    text = sep.join([U("a", 1), U("a", 2), U("b", 3)])
    groups, report = parse_links(text)
    assert report["total"] == 3
    assert [i["id"] for i in groups["a"]] == ["1", "2"]


def test_crlf_bom_and_blank_lines():
    text = "﻿" + U("a", 1) + "\r\n\r\n   \r\n" + U("a", 2) + "\r\n"
    groups, report = parse_links(text)
    assert [i["id"] for i in groups["a"]] == ["1", "2"]
    assert report["invalid"] == []


def test_duplicates_removed_keep_first_order():
    text = "\n".join([U("a", 1), U("a", 2), U("a", 1) + "?x=1", U("a", 2, "photo"), U("a", 3)])
    groups, report = parse_links(text)
    assert [i["id"] for i in groups["a"]] == ["1", "2", "3"]
    assert report["duplicates"] == 2 and report["total"] == 3


def test_same_pseudo_different_case_is_one_group_original_case_kept():
    groups, _ = parse_links(U("Alice", 1) + "\n" + U("ALICE", 2))
    assert list(groups) == ["alice"]
    assert [i["id"] for i in groups["alice"]] == ["1", "2"]
    assert groups["alice"][0]["username"] == "Alice"


def test_short_links_ignored_and_counted_not_invalid():
    text = "\n".join(["https://vm.tiktok.com/ZMabc123/", "https://vt.tiktok.com/ZSxyz/", U("a", 1)])
    groups, report = parse_links(text)
    assert report["ignored"] == 2 and report["invalid"] == []
    assert list(groups) == ["a"]


def test_noise_lines_reported_as_invalid_with_limit():
    lines = [f"junk line {i}" for i in range(9)] + [U("a", 1), "https://www.tiktok.com/@a"]
    groups, report = parse_links("\n".join(lines))
    assert report["total"] == 1
    assert report["invalid_count"] == 10
    assert len(report["invalid"]) == links_import.MAX_INVALID_REPORTED
    assert report["invalid"][0] == "junk line 0"


def test_long_invalid_line_truncated():
    _, report = parse_links("x" * 1000)
    assert len(report["invalid"][0]) == links_import.MAX_INVALID_LINE_LEN


def test_comment_lines_skipped():
    groups, report = parse_links("# export\n" + U("a", 1))
    assert report["invalid"] == [] and report["total"] == 1


def test_noise_around_url_on_same_line():
    groups, _ = parse_links('Voir "' + U("a", 5) + '" (super) !')
    assert groups["a"][0]["id"] == "5"


def test_non_tiktok_and_profile_urls_are_invalid():
    text = "\n".join(["https://example.com/@a/video/1", "https://www.tiktok.com/@a",
                      "https://www.tiktok.com/@a/live", "https://nottiktok.com/@a/video/9"])
    groups, report = parse_links(text)
    assert groups == {} and report["invalid_count"] == 4


def test_id_followed_by_letters_rejected():
    groups, report = parse_links("https://www.tiktok.com/@a/video/123abc")
    assert groups == {} and report["invalid_count"] == 1


def test_username_with_dots_dash_underscore_digits():
    groups, _ = parse_links(U("a.b-c_d9", 1))
    assert "a.b-c_d9" in groups


@pytest.mark.parametrize("bad", ["..", ".", "...", "a/b", "a\\b", "a b", "", "x" * 65])
def test_invalid_usernames_rejected(bad):
    assert not links_import.is_valid_username(bad)


def test_valid_usernames_accepted():
    for ok in ["bob", "a.b", "a-b", "a_b", "Bob99", "x" * 64]:
        assert links_import.is_valid_username(ok)


@pytest.mark.parametrize("evil", [
    "https://www.tiktok.com/@../video/1",
    "https://www.tiktok.com/@../../etc/video/1",
    "https://www.tiktok.com/@..%2f..%2fx/video/1",
    "https://www.tiktok.com/@a/../video/1",
    "https://www.tiktok.com/@..\\evil/video/1",
])
def test_path_traversal_pseudos_never_become_groups(evil):
    groups, _ = parse_links(evil)
    for key, items in groups.items():
        assert links_import.is_valid_username(key)
        assert "/" not in key and "\\" not in key and key.strip(".") != ""
        for item in items:
            assert ".." not in item["username"]


def test_empty_and_non_string_input():
    assert parse_links("")[0] == {}
    assert parse_links(None)[0] == {}
    assert parse_links("   \n\n")[1]["invalid"] == []


def test_unicode_digits_not_taken_as_ids():
    # \d accepte les chiffres Unicode : l'id est conservé tel quel mais reste numérique
    groups, _ = parse_links(U("a", 123))
    assert groups["a"][0]["id"].isdigit()


def test_large_input_is_fast_and_exact():
    text = "\n".join(U("u%d" % (i % 7), 10_000 + i) + "?a=1" for i in range(5000))
    groups, report = parse_links(text)
    assert report["total"] == 5000 and len(groups) == 7


def test_folder_name_matches_existing_directory_case_insensitively(tmp_path):
    (tmp_path / "Alice").mkdir()
    (tmp_path / "bob.txt").write_text("x")
    assert links_import.folder_name("alice", str(tmp_path)) == "Alice"
    assert links_import.folder_name("ALICE", str(tmp_path)) == "Alice"
    assert links_import.folder_name("carol", str(tmp_path)) == "carol"
    assert links_import.folder_name("bob.txt", str(tmp_path)) == "bob.txt"  # fichier, pas dossier
    assert links_import.folder_name("x", str(tmp_path / "absent")) == "x"


# ---------------------------------------------------------------- build_plan

def _groups(*pairs):
    return parse_links("\n".join(U(u, n) for u, n in pairs))[0]


def test_build_plan_by_author_is_default_and_keeps_order():
    groups = _groups(("alice", 1), ("bob", 2), ("alice", 3))
    plan = links_import.build_plan(groups)
    assert [(name, [i["id"] for i in items]) for name, items in plan] == [
        ("alice", ["1", "3"]), ("bob", ["2"])]


def test_build_plan_single_keeps_global_order():
    groups = _groups(("alice", 1), ("bob", 2), ("alice", 3), ("carol", 4))
    plan = links_import.build_plan(groups, mode="single", destination="zed")
    assert len(plan) == 1 and plan[0][0] == "zed"
    assert [i["id"] for i in plan[0][1]] == ["1", "2", "3", "4"]


def test_build_plan_resolves_case_from_existing_folders():
    groups = _groups(("bob", 1))
    assert links_import.build_plan(groups, existing_folders=["Bob", "x"])[0][0] == "Bob"
    assert links_import.build_plan(groups, mode="single", destination="BOB",
                                   existing_folders=["Bob"])[0][0] == "Bob"
    assert links_import.build_plan(groups, mode="single", destination="BOB")[0][0] == "BOB"


@pytest.mark.parametrize("bad", [None, "", "..", "a/b", "a\b", "a b", "x" * 80, 5])
def test_build_plan_single_validates_destination(bad):
    with pytest.raises(ValueError):
        links_import.build_plan(_groups(("a", 1)), mode="single", destination=bad)


def test_build_plan_validates_pseudo_and_mode():
    with pytest.raises(ValueError):
        links_import.build_plan({"x": [{"id": "1", "url": "u", "username": "../x"}]})
    with pytest.raises(ValueError):
        links_import.build_plan(_groups(("a", 1)), mode="autre")


def test_build_plan_is_pure_and_handles_empty():
    assert links_import.build_plan({}) == []
    assert links_import.build_plan({}, mode="single", destination="a") == []
