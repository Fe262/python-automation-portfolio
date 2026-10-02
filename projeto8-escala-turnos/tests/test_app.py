"""Smoke test: the Streamlit app loads, builds the sample schedule and reports a bad week clearly."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest


def test_app_builds_sample_schedule():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not at.exception
    assert [m.label for m in at.metric] == ["Status", "Preferred days off missed", "Busiest vs lightest"]
    assert at.metric[0].value in ("Optimal", "Feasible")


def test_app_explains_impossible_week():
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    at.number_input(key="wk1").set_value(8).run()  # 8 people on every weekday afternoon: team can't cover that
    at.button[0].click().run()
    assert at.error and "No valid schedule" in at.error[0].value
