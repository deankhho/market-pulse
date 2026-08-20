from unittest.mock import patch
from fetch_oi import _run_selftest, _run_live_check
import pandas as pd

def test_run_selftest_invokes_pytest():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        code = _run_selftest()
        assert code == 0
        assert "pytest" in mock_run.call_args[0][0]

def test_run_live_check_reports_success(monkeypatch):
    fixture = pd.read_csv("tests/fixtures/2026-08-19_regular.csv", dtype={"到期月份(週別)": str})

    class FakeTaifex:
        @staticmethod
        def options_daily(*a, **kw):
            return fixture

    monkeypatch.setattr("twchips.taifex", FakeTaifex)
    code = _run_live_check()
    assert code == 0
