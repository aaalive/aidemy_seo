"""Opt-in checks against the REAL services: `pytest -m live`. They catch API shape changes
that offline fixtures can't. The Data API part needs YOUTUBE_API_KEY (costs ~3 units)."""

import os

import pytest

from aidemy_seo import Autocomplete
from aidemy_seo.youtube_api import YouTubeAPI

pytestmark = pytest.mark.live


def test_live_autocomplete_returns_demand():
    d = Autocomplete().demand("Photosynthese")
    assert d >= 1, "autocomplete unreachable or response shape changed"


@pytest.mark.skipif(not os.environ.get("YOUTUBE_API_KEY"), reason="no YOUTUBE_API_KEY")
def test_live_data_api_channel_lookup():
    ch = YouTubeAPI().channel("@YouTube")
    assert ch and ch["uploads"].startswith("UU")
