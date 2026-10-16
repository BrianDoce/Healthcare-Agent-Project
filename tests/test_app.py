from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from agent.db import DEFAULT_DB

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


@pytest.mark.skipif(not Path(DEFAULT_DB).exists(), reason="run the pipeline first")
def test_app_renders_without_calling_the_model():
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert at.title[0].value == "Ask the hospital data"
    assert "Synthetic data only" in at.caption[0].value
    assert at.selectbox[0].options == ["claude-haiku-5-5", "claude-sonnet-5-5"]
