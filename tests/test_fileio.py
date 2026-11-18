"""Shared file helpers (src/aidemy_seo/fileio.py): the atomic writer used by the A/B commands and the
experiment ledger, and the CSV warning type. Offline."""

import json
import os
import stat
from datetime import datetime, timezone

import pytest

from aidemy_seo import experiments as ex
from aidemy_seo.fileio import CsvWarning, write_text_atomic

NOW = datetime(2026, 11, 18, tzinfo=timezone.utc)


def mode(path):
    return stat.S_IMODE(path.stat().st_mode)


def test_write_text_atomic_modes(tmp_path):
    old = os.umask(0o022)
    try:
        write_text_atomic(tmp_path / "normal.csv", "a,b\n")
        assert mode(tmp_path / "normal.csv") == 0o644  # default: normal permissions
        write_text_atomic(tmp_path / "private.json", "{}\n", new_file_mode=0o600)
        assert mode(tmp_path / "private.json") == 0o600
        (tmp_path / "normal.csv").chmod(0o640)
        write_text_atomic(tmp_path / "normal.csv", "c,d\n", new_file_mode=0o600)
        assert mode(tmp_path / "normal.csv") == 0o640  # an existing file keeps its mode
    finally:
        os.umask(old)
    assert (tmp_path / "normal.csv").read_bytes() == b"c,d\n"  # '\n' stays '\n' on every system
    assert sorted(p.name for p in tmp_path.iterdir()) == ["normal.csv", "private.json"]  # no temp file left


def test_new_ledger_is_private_through_the_shared_writer(tmp_path, monkeypatch):
    old = os.umask(0o022)
    try:
        path = tmp_path / "experiments.json"
        ex.assign(path, experiment="e", key="k1", keyword="Mitose", arms=["question", "warum"], now=NOW)
    finally:
        os.umask(old)
    assert mode(path) == 0o600  # a new ledger is private (specs/experiments.md), unlike the A/B outputs
    assert json.loads(path.read_text(encoding="utf-8"))["experiments"]["e"]["assignments"]["k1"]["arm"]
    calls = []
    real = ex.write_text_atomic

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(ex, "write_text_atomic", spy)
    ex.assign(path, experiment="e", key="k2", keyword="Zelle", now=NOW)
    assert calls == [{"new_file_mode": 0o600}]  # the ledger is written by fileio.write_text_atomic


def test_csv_warning_skipped_row_is_keyword_only():
    assert CsvWarning(3, "skipped - empty title", skipped_row=True).skipped_row is True
    assert CsvWarning(None, "ignored columns: views").skipped_row is False
    with pytest.raises(TypeError):
        CsvWarning(3, "skipped - empty title", True)  # a bare True says nothing - use skipped_row=True
