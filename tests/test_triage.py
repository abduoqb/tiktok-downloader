"""Tests de triage (fonctions pures, aucune E/S)."""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from triage import (CATEGORIES, TriageContext, classify_id, classify_links,  # noqa: E402
                    estimate_seconds)
from disk_index import DiskEntry  # noqa: E402

NOW = datetime(2025, 1, 1, 12, 0, 0)


def st(status, next_retry=None):
    return {"status": status, "attempts": 1, "next_retry": next_retry}


def ctx(**kw):
    return TriageContext(**kw)


def test_rules_basic():
    assert classify_id("1", ctx()) == "new"
    assert classify_id("1", ctx(history_success={"1"})) == "downloaded"
    assert classify_id("1", ctx(state={"1": st("ignored")})) == "ignored"
    assert classify_id("1", ctx(disk={"1": None})) == "adopt"
    assert classify_id("1", ctx(disk={"1"})) == "adopt"
    assert classify_id("1", ctx(state={"1": st("unavailable")})) == "unavailable"
    assert classify_id("1", ctx(history_failed={"1"})) == "retry_due"
    assert classify_id(1, ctx(history_success={"1"})) == "downloaded"


def test_retry_timing():
    future = (NOW + timedelta(seconds=5)).isoformat()
    past = (NOW - timedelta(seconds=5)).isoformat()
    assert classify_id("1", ctx(state={"1": st("retry", future)}), now=NOW) == "retry_waiting"
    assert classify_id("1", ctx(state={"1": st("retry", past)}), now=NOW) == "retry_due"
    assert classify_id("1", ctx(state={"1": st("retry", None)}), now=NOW) == "retry_due"
    assert classify_id("1", ctx(state={"1": st("retry", future)}), now=NOW,
                       force_update=True) == "retry_due"


def test_priorities():
    c = ctx(history_success={"1"}, state={"1": st("ignored")}, disk={"1"})
    assert classify_id("1", c) == "downloaded"
    c = ctx(state={"1": st("ignored")}, disk={"1"})
    assert classify_id("1", c) == "ignored"
    assert classify_id("1", c, force_update=True) == "ignored"
    c = ctx(state={"1": st("unavailable")}, disk={"1"})
    assert classify_id("1", c) == "adopt"
    c = ctx(state={"1": st("retry")}, history_failed={"1"})
    assert classify_id("1", c, now=NOW) == "retry_due"
    c = ctx(state={"1": st("unavailable")}, history_failed={"1"})
    assert classify_id("1", c) == "unavailable"
    assert classify_id("1", c, force_update=True) == "retry_due"
    c = ctx(history_failed={"1"}, history_success={"1"})
    assert classify_id("1", c) == "downloaded"


def L(i, url=True):
    d = {"id": i}
    if url:
        d["url"] = f"https://www.tiktok.com/@u/video/{i}"
    return d


def test_classify_links_invalid_duplicate_types():
    items = [L(10), L(10), {"id": "", "url": "x"}, {"url": "x"}, L(11, url=False),
             L("12"), L(12), {"id": None, "url": "x"}]
    r = classify_links(items, ctx(), now=NOW)
    assert r.counts["new"] == 2
    assert r.counts["duplicate"] == 2
    assert r.counts["invalid"] == 4
    assert r.total == 8
    assert [i["id"] for i in r.to_process] == [10, "12"]
    assert set(r.counts) == set(CATEGORIES)


def test_to_adopt_and_order():
    entry = DiskEntry(id="2", kind="video")
    c = ctx(disk={"2": entry, "3": entry})
    r = classify_links([L(1), L(2), L(3), L(4)], c)
    assert [i["id"] for i in r.to_process] == [1, 4]
    assert [(i["id"], e) for i, e in r.to_adopt] == [(2, entry), (3, entry)]
    r2 = classify_links([L(2)], ctx(disk={"2"}))
    assert r2.to_adopt[0][1] is None


def test_plan_hash():
    c = ctx(history_success={"5"})
    a = classify_links([L(1), L(2), L(5)], c)
    b = classify_links([L(1), dict(reversed(list(L(2).items()))), L(5)], c)
    assert a.plan_hash("D:/Out", False) == b.plan_hash("d:/out", False)
    assert a.plan_hash("D:/Out", False) != a.plan_hash("D:/Out", True)
    assert a.plan_hash("D:/Out", False) != a.plan_hash("D:/Other", False)
    swapped = classify_links([L(2), L(1), L(5)], c)
    assert a.plan_hash("x", False) != swapped.plan_hash("x", False)
    assert len(a.plan_hash("x", False)) == 40


def test_sample():
    r = classify_links([L(i) for i in range(30)], ctx())
    s = r.sample(5)
    assert set(s) == set(CATEGORIES)
    assert len(s["new"]) == 5 and s["new"][0] == ("0", L(0)["url"])
    assert len(r.sample()["new"]) == 20
    assert s["adopt"] == []


def test_estimate_seconds():
    assert estimate_seconds(0, 1, 3) == 0
    assert estimate_seconds(-2, 1, 3) == 0
    assert estimate_seconds(1, 2, 4) == 6
    assert estimate_seconds(11, 2, 4) == 10 * 3 + 66


def test_thousand_links_mixed():
    items = [L(i) for i in range(1000)]
    items += [L(0), L(1)]
    items += [{"id": "", "url": ""}]
    future = (NOW + timedelta(hours=1)).isoformat()
    past = (NOW - timedelta(hours=1)).isoformat()
    state = {}
    state.update({str(i): st("ignored") for i in range(400, 450)})
    state.update({str(i): st("unavailable") for i in range(450, 550)})
    state.update({str(i): st("retry", future) for i in range(550, 650)})
    state.update({str(i): st("retry", past) for i in range(650, 700)})
    c = ctx(history_success={str(i) for i in range(0, 200)},
            history_failed={str(i) for i in range(200, 250)},
            disk={str(i) for i in range(250, 400)},
            state=state)
    r = classify_links(items, c, now=NOW)
    assert r.counts["downloaded"] == 200
    assert r.counts["retry_due"] == 100
    assert r.counts["adopt"] == 150
    assert r.counts["ignored"] == 50
    assert r.counts["unavailable"] == 100
    assert r.counts["retry_waiting"] == 100
    assert r.counts["new"] == 300
    assert r.counts["duplicate"] == 2 and r.counts["invalid"] == 1
    assert sum(r.counts.values()) == r.total == 1003
    assert len(r.to_process) == 400 and len(r.to_adopt) == 150
    f = classify_links(items, c, now=NOW, force_update=True)
    assert f.counts["unavailable"] == 0 and f.counts["retry_waiting"] == 0
    assert f.counts["retry_due"] == 50 + 100 + 100 + 50
