import pandas as pd
import pytest
from market_observation import compute_observation

@pytest.fixture
def real_chain():
    return pd.read_csv("tests/fixtures/2026-08-19_regular.csv", dtype={"到期月份(週別)": str})

def test_compute_observation_returns_expected_shape(real_chain):
    obs = compute_observation(real_chain, "202608")
    assert set(obs.keys()) == {"call_wall", "put_wall", "call_top3", "put_top3", "distribution"}
    assert isinstance(obs["call_wall"], int)
    assert isinstance(obs["put_wall"], int)
    assert len(obs["call_top3"]) <= 3
    assert set(obs["distribution"].keys()) == {"call", "put"}

def test_compute_observation_deterministic(real_chain):
    """同一份輸入資料跑兩次，wall/top3完全相同（spec: Observation invariants）"""
    obs1 = compute_observation(real_chain, "202608")
    obs2 = compute_observation(real_chain, "202608")
    assert obs1 == obs2

def test_wall_exists_in_distribution(real_chain):
    """call_wall/put_wall一定存在於distribution裡（spec: Observation invariants）"""
    obs = compute_observation(real_chain, "202608")
    assert str(obs["call_wall"]) in obs["distribution"]["call"]
    assert str(obs["put_wall"]) in obs["distribution"]["put"]

def test_distribution_keys_are_stringified_integers(real_chain):
    """distribution的履約價key一律字串化整數，不是帶小數點的字串"""
    obs = compute_observation(real_chain, "202608")
    for key in obs["distribution"]["call"]:
        assert key == str(int(key))  # "24000" 而非 "24000.0"

def test_tie_break_not_row_order_dependent():
    """同OI值時取履約價較小者，跟原始列順序無關（不受pandas row order影響）"""
    fake = pd.DataFrame({
        "到期月份(週別)": ["202608"] * 4,
        "履約價": [24100.0, 24000.0, 24200.0, 23900.0],  # 刻意打亂順序
        "買賣權": ["買權"] * 4,
        "未沖銷契約數": [500.0, 500.0, 300.0, 100.0],  # 前兩個同量並列最大
    })
    obs = compute_observation(fake, "202608")
    assert obs["call_wall"] == 24000  # 同量取履約價較小者，不是先出現的24100
