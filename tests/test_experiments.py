"""Title template experiments (specs/experiments.md): hash assignment, JSON ledger, age-fair report
with a bootstrap confidence interval. Offline; every test pins `now`."""

import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aidemy_seo import experiments as ex
from aidemy_seo.experiments import (
    ARMS,
    INSUFFICIENT_DATA,
    NO_WINNER_YET,
    NOT_PUBLISHED,
    WINNER,
    ExperimentError,
    assign,
    assign_arm,
    bootstrap_ci,
    load_ledger,
    report,
)
from aidemy_seo.titles import TEMPLATES

NOW = datetime(2026, 11, 15, tzinfo=timezone.utc)
SRC = Path(__file__).resolve().parent.parent / "src"
PINNED = ("hook-2026-11", "bio-kl10-gentechnik")  # -> musst_du_wissen (sha256 prefix 3e1ea3cee164415a)
TWO = ["question", "musst_du_wissen"]


def ts(days_ago: float) -> str:
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def experiment(per_arm: dict, *, days_ago: float = 10, name: str = "e"):
    """A ledger + stats videos where arm -> list of views per day (all published `days_ago`)."""
    ledger = {"version": 1, "experiments": {name: {"created_at": ts(30), "arms": {}, "assignments": {}}}}
    exp = ledger["experiments"][name]
    videos = []
    for arm, per_day in per_arm.items():
        exp["arms"][arm] = ARMS[arm]
        for i, vpd in enumerate(per_day):
            title = f"Thema {arm} {i} #Bio"
            exp["assignments"][f"{arm}-{i}"] = {"arm": arm, "title": title}
            videos.append({"title": title, "went_public_at": ts(days_ago), "views": vpd * days_ago})
    return ledger, videos


# ---------------------------------------------------------------- arms and assignment
def test_every_template_has_one_arm_name():
    assert sorted(ARMS.values()) == sorted(TEMPLATES) and len(ARMS) == len(TEMPLATES) == len(set(TEMPLATES))
    assert {v: k for k, v in ARMS.items()}[TEMPLATES[0]] == "question"


def test_assign_arm_is_deterministic_and_pinned():
    assert [assign_arm(*PINNED, TWO) for _ in range(5)] == ["musst_du_wissen"] * 5
    assert assign_arm(PINNED[0], f"  {PINNED[1]} ", TWO) == "musst_du_wissen"  # the key is stripped
    # the documented recipe, spelled out - a change to the algorithm must fail here
    import hashlib

    digest = hashlib.sha256(json.dumps(list(PINNED), ensure_ascii=False).encode("utf-8")).hexdigest()
    assert digest[:16] == "3e1ea3cee164415a" and sorted(TWO)[int(digest[:16], 16) % 2] == "musst_du_wissen"


def test_assign_arm_ignores_pythonhashseed():
    code = (
        "from aidemy_seo.experiments import assign_arm;"
        f"print(assign_arm({PINNED[0]!r}, {PINNED[1]!r}, {TWO!r}), hash({PINNED[1]!r}))"
    )
    out = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(SRC)}
        res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True)
        out.append(res.stdout.split())
    assert out[0][0] == out[1][0] == "musst_du_wissen"
    assert out[0][1] != out[1][1]  # proof the seeds really differ: Python's own hash() changed


def test_assign_arm_order_of_arms_does_not_matter():
    arms = ["warum", "question", "endlich"]
    for key in (f"lesson-{i}" for i in range(50)):
        assert assign_arm("e", key, arms) == assign_arm("e", key, arms[::-1]) == assign_arm("e", key, set(arms))


def test_assign_arm_is_roughly_balanced():
    counts = Counter(
        assign_arm("hook-2026-11", f"lesson-{i}", ["question", "musst_du_wissen", "warum"]) for i in range(600)
    )
    assert set(counts) == {"question", "musst_du_wissen", "warum"}
    assert all(160 <= n <= 240 for n in counts.values()), counts


def test_experiments_are_independent():
    assert assign_arm("hook-2026-11", PINNED[1], TWO) == "musst_du_wissen"
    assert assign_arm("hook-2026-12", PINNED[1], TWO) == "question"
    keys = [f"lesson-{i}" for i in range(200)]
    assert any(assign_arm("hook-2026-11", k, TWO) != assign_arm("hook-2026-12", k, TWO) for k in keys)
    # json.dumps of the pair, not "name:key": joined with ":" these pairs would hash the SAME text
    # ("x:7:y") and always get the same arm; as separate JSON strings they are independent draws
    assert any(assign_arm(f"x:{i}", "y", TWO) != assign_arm("x", f"{i}:y", TWO) for i in range(50))


def test_assign_rejects_bad_key_and_arms(tmp_path):
    ledger = tmp_path / "l.json"
    for bad in ("", "   "):
        with pytest.raises(ExperimentError, match="key must not be empty"):
            assign_arm("e", bad, TWO)
        with pytest.raises(ExperimentError, match="key must not be empty"):
            assign(ledger, experiment="e", key=bad, keyword="Gentechnik", arms=TWO)
    with pytest.raises(ExperimentError, match="experiment name must not be empty"):
        assign(ledger, experiment=" ", key="k", keyword="Gentechnik", arms=TWO)
    with pytest.raises(ExperimentError, match="at least 2 arms, got 1"):
        assign(ledger, experiment="e", key="k", keyword="Gentechnik", arms=["question"])
    with pytest.raises(ExperimentError, match="arm listed twice: question"):
        assign(ledger, experiment="e", key="k", keyword="Gentechnik", arms=["question", "question"])
    with pytest.raises(ExperimentError, match="unknown arm clickbait - choose from question"):
        assign(ledger, experiment="e", key="k", keyword="Gentechnik", arms=["question", "clickbait"])
    with pytest.raises(ExperimentError, match="keyword must not be empty"):
        assign(ledger, experiment="e", key="k", keyword=" ", arms=TWO)
    assert not ledger.exists()  # nothing was written by any refused assign


def test_assign_never_redraws_for_long_or_colon_titles(tmp_path):
    # the pinned key lands on musst_du_wissen = "{x}: Das musst du wissen!"
    colon = assign(
        tmp_path / "a.json",
        experiment=PINNED[0],
        key=PINNED[1],
        keyword="Indien bis Kongo: Dekolonisierung",
        arms=TWO,
        now=NOW,
    )
    assert colon.arm == "musst_du_wissen" and colon.title.count(":") == 2
    assert any("two ':'" in w and "arm kept on purpose" in w for w in colon.warnings)
    long_kw = "Nutzen und Risiken ausgewählter transgener Organismen im Überblick"
    long = assign(tmp_path / "b.json", experiment=PINNED[0], key=PINNED[1], keyword=long_kw, arms=TWO, now=NOW)
    assert long.arm == assign_arm(*PINNED, TWO) == "musst_du_wissen" and len(long.title) > 66
    assert any("over 66" in w for w in long.warnings)
    fine = assign(tmp_path / "c.json", experiment=PINNED[0], key=PINNED[1], keyword="Gentechnik", arms=TWO, now=NOW)
    assert fine.arm == "musst_du_wissen" and fine.warnings == []


# ---------------------------------------------------------------- ledger
def test_ledger_assign_is_idempotent_and_persists(tmp_path):
    path = tmp_path / "experiments.json"
    first = assign(
        path,
        experiment=PINNED[0],
        key=PINNED[1],
        keyword="Gentechnik",
        subject="Biologie",
        grade="Klasse 10",
        arms=TWO,
        now=NOW,
    )
    assert path.exists() and not first.already_assigned
    assert first.title == "Gentechnik: Das musst du wissen! #Biologie #Klasse10"
    before = path.read_bytes()
    again = assign(path, experiment=PINNED[0], key=PINNED[1], keyword="Anders", now=NOW + timedelta(days=3))
    assert again.already_assigned and path.read_bytes() == before
    assert (again.arm, again.title, again.assigned_at) == (first.arm, first.title, "2026-11-15T00:00:00+00:00")
    exp = load_ledger(path)["experiments"][PINNED[0]]
    assert list(exp["assignments"]) == [PINNED[1]] and exp["created_at"] == "2026-11-15T00:00:00+00:00"
    assert exp["arms"] == {a: ARMS[a] for a in TWO}  # template text is stored with the experiment
    # no --arm later = keep the stored arms; all 6 templates when a new experiment starts without --arm
    assign(path, experiment=PINNED[0], key="second", keyword="Zellatmung", now=NOW)
    assign(path, experiment="all-arms", key="k", keyword="Zellatmung", now=NOW)
    assert set(load_ledger(path)["experiments"]["all-arms"]["arms"]) == set(ARMS)


def test_ledger_rejects_changed_arms(tmp_path):
    path = tmp_path / "l.json"
    assign(path, experiment="e", key="k1", keyword="Gentechnik", arms=["question", "warum"], now=NOW)
    before = path.read_bytes()
    with pytest.raises(ExperimentError, match="arms can't change"):
        assign(path, experiment="e", key="k2", keyword="Zellatmung", arms=["question", "endlich"], now=NOW)
    assert path.read_bytes() == before
    # the same set in another order is not a change
    assign(path, experiment="e", key="k2", keyword="Zellatmung", arms=["warum", "question"], now=NOW)


def test_ledger_rejects_duplicate_title(tmp_path):
    path = tmp_path / "l.json"
    # same arm + same keyword = same title: pick two keys that the hash puts on the same arm
    keys = [k for k in (f"lesson-{i}" for i in range(20)) if assign_arm("e", k, TWO) == "question"][:2]
    assign(path, experiment="e", key=keys[0], keyword="Gentechnik", arms=TWO, now=NOW)
    before = path.read_bytes()
    with pytest.raises(ExperimentError, match=f"already used by key '{keys[0]}'"):
        assign(path, experiment="e", key=keys[1], keyword="Gentechnik", now=NOW)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{not json", "is not valid JSON"),
        ('{"version": 2, "experiments": {}}', "version 2 is not supported"),
        ("[]", "top level must be a JSON object"),
        ('{"version": 1, "experiments": []}', '"experiments" must be an object'),
        ('{"version": 1, "experiments": {"e": {"arms": {}}}}', 'needs "arms" and "assignments"'),
        ('{"version": 1, "experiments": {"e": {"arms": {"a": "{x}"}, "assignments": {}}}}', "at least 2 arms"),
        (
            '{"version": 1, "experiments": {"e": {"arms": {"a": "{x}", "b": "{x}!"}, "assignments": {"k": {"arm": "z"}}}}}',
            "needs an arm of that experiment",
        ),
    ],
    ids=["not-json", "version-2", "list", "experiments-list", "no-assignments", "one-arm", "unknown-arm"],
)
def test_ledger_bad_file_is_an_error_and_untouched(tmp_path, content, message):
    path = tmp_path / "l.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ExperimentError, match=message):
        load_ledger(path)
    with pytest.raises(ExperimentError, match="the file was not changed"):
        assign(path, experiment="e", key="k", keyword="Gentechnik", arms=TWO, now=NOW)
    assert path.read_text(encoding="utf-8") == content


def test_ledger_write_is_atomic_and_readable(tmp_path, monkeypatch):
    path = tmp_path / "l.json"
    # hook-2026-12 puts the pinned key on "question" -> the title has an "ä"
    assign(path, experiment="hook-2026-12", key=PINNED[1], keyword="Gentechnik", arms=TWO, now=NOW)
    assert [p.name for p in tmp_path.iterdir()] == ["l.json"]  # no temp file left behind
    text = path.read_text(encoding="utf-8")
    assert "erklären" in text and "\\u00e4" not in text and text.startswith('{\n  "experiments": {')
    assert text == json.dumps(json.loads(text), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.chmod(0o644)
    assign(path, experiment="hook-2026-12", key="second", keyword="Zellatmung", now=NOW)
    assert path.stat().st_mode & 0o777 == 0o644  # an existing ledger keeps its file mode
    # a crash between writing and replacing leaves the old file intact and no temp file
    before = path.read_bytes()

    def crash(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(ex.os, "replace", crash)
    with pytest.raises(OSError, match="disk full"):
        assign(path, experiment="hook-2026-12", key="third", keyword="Mitose", now=NOW)
    assert path.read_bytes() == before and [p.name for p in tmp_path.iterdir()] == ["l.json"]


# ---------------------------------------------------------------- report
def test_report_insufficient_data_per_arm():
    rep = report(*experiment({"question": [30, 31, 32], "musst_du_wissen": [10, 11, 12]}), experiment="e", now=NOW)
    assert rep.verdict == INSUFFICIENT_DATA and rep.winner is None and rep.leader is None and rep.comparisons == []
    assert all(a.lift is None and a.verdict == "not enough data (need 5 per arm)" for a in rep.arms)
    text = "\n".join(rep.lines())
    assert "insufficient data - need 5 used videos per arm: musst_du_wissen needs 2 more, question needs 2 more" in text
    assert "WINNER" not in text and "leader" not in text


def test_report_is_age_fair():
    ledger, vids = experiment({"question": [30] * 6})  # 10 days old, 300 views each
    more_ledger, old = experiment({"musst_du_wissen": [10] * 6}, days_ago=90)  # 900 views each
    ledger["experiments"]["e"]["arms"].update(more_ledger["experiments"]["e"]["arms"])
    ledger["experiments"]["e"]["assignments"].update(more_ledger["experiments"]["e"]["assignments"])
    fair = report(ledger, vids + old, experiment="e", now=NOW)
    by_arm = {a.arm: a for a in fair.arms}
    assert (by_arm["question"].lift, by_arm["question"].verdict) == (3.0, "helps")
    assert by_arm["musst_du_wissen"].verdict == "hurts"
    assert (fair.verdict, fair.winner) == (WINNER, "question")
    raw = report(ledger, vids + old, experiment="e", now=NOW, metric="views")  # the age trap
    assert (raw.verdict, raw.winner) == (WINNER, "musst_du_wissen")
    assert {a.arm: a.verdict for a in raw.arms} == {"question": "hurts", "musst_du_wissen": "helps"}


def test_report_lists_unmatched_and_ignores_unassigned_videos():
    ledger, vids = experiment({"question": [30] * 5, "musst_du_wissen": [10] * 5})
    exp = ledger["experiments"]["e"]
    exp["assignments"]["late"] = {"arm": "question", "title": "Not uploaded yet"}
    exp["assignments"]["twice"] = {"arm": "question", "title": "Uploaded twice"}
    vids += [
        {"title": "Someone else's upload", "went_public_at": ts(10), "views": 99_999},  # not in the ledger
        {"title": "Uploaded  twice", "went_public_at": ts(10), "views": 1},  # whitespace is collapsed
        {"title": "Uploaded twice", "went_public_at": ts(10), "views": 2},
    ]
    rep = report(ledger, vids, experiment="e", now=NOW)
    assert rep.unmatched == [
        {"key": "late", "arm": "question", "title": "Not uploaded yet", "reason": NOT_PUBLISHED},
        {
            "key": "twice",
            "arm": "question",
            "title": "Uploaded twice",
            "reason": "title matches 2 videos in the stats file",
        },
    ]
    q = next(a for a in rep.arms if a.arm == "question")
    assert (q.assigned, q.published, q.used, q.median) == (7, 5, 5, 30.0)  # the 99,999 never counted
    assert rep.assigned == 12 and rep.used == 10
    assert rep.left_out == {NOT_PUBLISHED: 1, "title matches 2 videos in the stats file": 1}
    assert "not counted:" in rep.lines() and any("late (question): not published yet" in ln for ln in rep.lines())


def test_report_default_min_age_skips_fresh_videos():
    ledger, vids = experiment({"question": [30] * 5, "musst_du_wissen": [10] * 5})
    ledger["experiments"]["e"]["assignments"]["fresh"] = {"arm": "question", "title": "Fresh"}
    vids.append({"title": "Fresh", "went_public_at": ts(3), "views": 3000})
    rep = report(ledger, vids, experiment="e", now=NOW)
    q = next(a for a in rep.arms if a.arm == "question")
    assert (q.published, q.used, q.median) == (6, 5, 30.0) and rep.left_out == {"outside the age window": 1}
    assert rep.min_age == 7.0 and "age >= 7 days" in rep.lines()[0]
    # with --min-age 0 the fresh video counts
    assert (
        next(a for a in report(ledger, vids, experiment="e", now=NOW, min_age=0).arms if a.arm == "question").used == 6
    )


# ---------------------------------------------------------------- confidence interval and verdict
def test_bootstrap_ci_is_deterministic_and_contains_ratio():
    a, b = [22, 25, 28, 30, 31, 33, 36, 40], [8, 9, 10, 10, 11, 12, 13, 15]
    ratio = 30.5 / 10.5
    lo, hi = bootstrap_ci(a, b, seed=0)
    assert (lo, hi) == bootstrap_ci(a, b, seed=0) == bootstrap_ci(a, b, rng=ex.seeded_rng(0))
    assert lo <= ratio <= hi
    lo99, hi99 = bootstrap_ci(a, b, seed=0, level=0.99)
    assert lo99 <= lo and hi99 >= hi and (lo99, hi99) != (lo, hi)
    with pytest.raises(ValueError, match="at least one value"):
        bootstrap_ci([], b)
    with pytest.raises(ValueError, match="between 0 and 1"):
        bootstrap_ci(a, b, level=1.0)


def test_report_clear_difference_is_a_winner():
    per_arm = {"question": [22, 25, 28, 30, 31, 33, 36, 40], "musst_du_wissen": [8, 9, 10, 10, 11, 12, 13, 15]}
    rep = report(*experiment(per_arm), experiment="e", now=NOW)
    assert (rep.verdict, rep.winner, rep.leader) == (WINNER, "question", "question")
    (c,) = rep.comparisons
    assert (c.arm, c.vs, c.level) == ("question", "musst_du_wissen", 0.95) and 1.0 < c.ci_low <= c.ratio <= c.ci_high
    assert rep.lines()[1].startswith("verdict: WINNER = question - beats every other arm (musst_du_wissen: ratio")
    assert "fixed the number of videos per arm in advance" in rep.lines()[2]
    assert report(*experiment(per_arm), experiment="e", now=NOW, seed=0) == rep  # same seed, same everything


def test_report_overlapping_arms_is_no_winner_yet():
    per_arm = {"question": [10, 14, 18, 22, 26, 30], "musst_du_wissen": [9, 13, 17, 21, 25, 29]}
    rep = report(*experiment(per_arm), experiment="e", now=NOW)
    assert (rep.verdict, rep.winner, rep.leader) == (NO_WINNER_YET, None, "question")
    assert rep.comparisons[0].ci_low <= 1.0 <= rep.comparisons[0].ci_high
    assert "no winner yet - leader question has not yet beaten musst_du_wissen" in rep.lines()[1]


def test_report_winner_must_beat_every_arm_with_bonferroni():
    per_arm = {
        "question": [22, 25, 28, 30, 31, 33],
        "warum": [20, 24, 27, 29, 30, 32],
        "musst_du_wissen": [8, 9, 10, 10, 11, 12],
    }
    rep = report(*experiment(per_arm), experiment="e", now=NOW)
    assert (rep.verdict, rep.leader) == (NO_WINNER_YET, "question")
    assert [c.level for c in rep.comparisons] == [0.975, 0.975]  # 1 - 0.05 / 2
    beaten = {c.vs: c.ci_low > 1.0 for c in rep.comparisons}
    assert beaten == {"musst_du_wissen": True, "warum": False}
    line = rep.lines()[1]
    assert "has not yet beaten warum (warum: ratio" in line and "97.5% CI" in line and "musst_du_wissen" not in line
    # both lead the pooled rest ("helps") - which is exactly why the descriptive lift never names a winner
    assert {a.arm: a.verdict for a in rep.arms}["warum"] == "helps"


def test_report_zero_median_gives_inf_bound_and_valid_json():
    rep = report(*experiment({"question": [1, 2, 3, 4, 5], "musst_du_wissen": [0] * 5}), experiment="e", now=NOW)
    data = json.loads(json.dumps(rep.to_json(), allow_nan=False))  # allow_nan=False: no Infinity sneaks in
    assert data["comparisons"][0]["ci_high"] == "inf" and data["comparisons"][0]["ratio"] == "inf"
    assert {a["arm"]: a["lift"] for a in data["arms"]} == {"musst_du_wissen": 0.0, "question": "inf"}
    spec_keys = "experiment metric min_age max_age now confidence seed verdict winner leader comparisons arms unmatched"
    assert set(spec_keys.split()) <= set(data)
    assert "ratio inf" in rep.lines()[1]
    assert ex._json_safe([-float("inf"), 1.5]) == ["-inf", 1.5]


def test_report_tie_picks_leader_by_name_and_no_winner():
    rep = report(
        *experiment({"warum": [10, 12, 14, 16, 18], "question": [10, 12, 14, 16, 18]}), experiment="e", now=NOW
    )
    assert (rep.leader, rep.verdict, rep.winner) == ("question", NO_WINNER_YET, None)
    zeros = report(*experiment({"warum": [0] * 5, "question": [0] * 5}), experiment="e", now=NOW)
    assert (zeros.leader, zeros.verdict, zeros.comparisons[0].ratio) == ("question", NO_WINNER_YET, 1.0)


def test_report_rejects_bad_options():
    ledger, vids = experiment({"question": [1] * 5, "musst_du_wissen": [1] * 5})
    with pytest.raises(ExperimentError, match="no experiment 'nope' in the ledger - it has: e"):
        report(ledger, vids, experiment="nope")
    for conf in (0, 1, 1.5, float("nan")):
        with pytest.raises(ExperimentError, match="confidence must be between 0 and 1"):
            report(ledger, vids, experiment="e", confidence=conf)
    with pytest.raises(ExperimentError, match="min_group must be at least 1"):
        report(ledger, vids, experiment="e", min_group=0)
    with pytest.raises(ExperimentError, match="larger than max age"):
        report(ledger, vids, experiment="e", min_age=30, max_age=7)
    with pytest.raises(ExperimentError, match="does not exist"):
        load_ledger("/nonexistent/ledger.json", must_exist=True)
