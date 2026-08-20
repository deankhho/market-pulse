import pandas as pd
import pytest
from validate import validate_chain, ABS_FLOOR

@pytest.fixture
def real_chain():
    return pd.read_csv("tests/fixtures/2026-08-19_regular.csv", dtype={"到期月份(週別)": str})

def test_validate_chain_passes_real_fixture(real_chain):
    ok, reason = validate_chain(real_chain, ABS_FLOOR)
    assert ok is True
    assert reason is None

def test_validate_chain_fails_on_missing_column(real_chain):
    broken = real_chain.drop(columns=["未沖銷契約數"])
    ok, reason = validate_chain(broken, ABS_FLOOR)
    assert ok is False
    assert "未沖銷契約數" in reason

def test_validate_chain_fails_on_too_few_rows(real_chain):
    tiny = real_chain.head(10)
    ok, reason = validate_chain(tiny, ABS_FLOOR)
    assert ok is False
    assert "下限" in reason

def test_validate_chain_fails_on_negative_oi(real_chain):
    broken = real_chain.copy()
    broken.loc[0, "未沖銷契約數"] = -5
    ok, reason = validate_chain(broken, ABS_FLOOR)
    assert ok is False
    assert "未沖銷契約數" in reason

def test_validate_chain_fails_on_duplicate_strike(real_chain):
    broken = pd.concat([real_chain, real_chain.iloc[[0]]], ignore_index=True)
    ok, reason = validate_chain(broken, ABS_FLOOR)
    assert ok is False
    assert "重複" in reason

def test_validate_chain_fails_on_missing_side(real_chain):
    broken = real_chain[real_chain["買賣權"] == "買權"]  # 只留call，沒有put
    ok, reason = validate_chain(broken, ABS_FLOOR)
    assert ok is False
    assert "買賣權" in reason
