import re
from datetime import date

import pandas as pd
import pytest

from contract_selection import select_contract, NoValidContractError


@pytest.fixture
def real_chain():
    return pd.read_csv("tests/fixtures/2026-08-19_regular.csv", dtype={"到期月份(週別)": str})


def test_select_contract_picks_nearest_monthly_series_excluding_expiry_day(real_chain):
    """2026-08-19 當天，202608 剛好到期（見 fixture README）。
    因為 到期日 >= data_date 用 >=（domain invariant，spec明確定案），
    到期日當天本身仍是候選，但 trading_days_until_expiry=0 <= 3 落入到期週規則，
    要被排除、改選次近月 202609。"""
    contract_month, expiry_date, reason = select_contract(
        real_chain, date(2026, 8, 19), holidays=set()
    )
    assert contract_month == "202609"
    assert "到期週" in reason or "trading_days" in reason


def test_select_contract_deterministic(real_chain):
    """同一份輸入資料跑兩次，結果完全相同（spec: Contract invariants）"""
    r1 = select_contract(real_chain, date(2026, 8, 19), set())
    r2 = select_contract(real_chain, date(2026, 8, 19), set())
    assert r1 == r2


def test_select_contract_excludes_weekly_series(real_chain):
    """週選（202608F3/202608F4/202608W4/202609W1）不該被選中"""
    contract_month, _, _ = select_contract(real_chain, date(2026, 8, 19), set())
    assert re.match(r"^\d{6}$", contract_month)


def test_select_contract_expiry_date_always_gte_data_date(real_chain):
    """選出的契約到期日一定 >= data_date（spec: Contract invariants）"""
    data_date = date(2026, 8, 19)
    _, expiry_date, _ = select_contract(real_chain, data_date, set())
    assert expiry_date >= data_date


def test_select_contract_raises_when_no_monthly_series():
    """全是週選、沒有任何月選 → 拋 NoValidContractError，不靜默回傳空值"""
    fake_chain = pd.DataFrame({
        "到期月份(週別)": ["202608F3", "202608F4"],
        "契約到期日": ["20260821", "20260828"],
    })
    with pytest.raises(NoValidContractError):
        select_contract(fake_chain, date(2026, 8, 19), set())


def test_select_contract_raises_when_all_expired():
    """所有候選契約到期日都早於 data_date → 拋例外，不回傳過期合約"""
    fake_chain = pd.DataFrame({
        "到期月份(週別)": ["202607"],
        "契約到期日": ["20260731"],
    })
    with pytest.raises(NoValidContractError):
        select_contract(fake_chain, date(2026, 8, 19), set())


from contract_selection import list_weekly_contracts


def test_list_weekly_contracts_returns_all_unexpired_sorted_by_expiry(real_chain):
    """2026-08-19真實fixture查證過的週選清單：202608F3(8/21)、
    202608W4(8/26)、202608F4(8/28)、202609W1(9/2)，全部未到期，
    依到期日排序（不是代號字串排序）。"""
    result = list_weekly_contracts(real_chain, date(2026, 8, 19))
    assert [cm for cm, _ in result] == [
        "202608F3", "202608W4", "202608F4", "202609W1",
    ]
    assert result[0] == ("202608F3", date(2026, 8, 21))
    assert result[1] == ("202608W4", date(2026, 8, 26))
    assert result[2] == ("202608F4", date(2026, 8, 28))
    assert result[3] == ("202609W1", date(2026, 9, 2))


def test_list_weekly_contracts_excludes_expired():
    """契約到期日 < data_date 的週選不列入清單。"""
    fake_chain = pd.DataFrame({
        "到期月份(週別)": ["202608F3", "202608F4"],
        "契約到期日": ["20260810", "20260828"],  # F3已過期(8/10 < 8/19)
    })
    result = list_weekly_contracts(fake_chain, date(2026, 8, 19))
    assert [cm for cm, _ in result] == ["202608F4"]


def test_list_weekly_contracts_empty_when_no_weekly_series():
    """全是月選、沒有任何週選 → 回傳空列表（不拋例外）。"""
    fake_chain = pd.DataFrame({
        "到期月份(週別)": ["202609", "202610"],
        "契約到期日": ["20260916", "20261021"],
    })
    result = list_weekly_contracts(fake_chain, date(2026, 8, 19))
    assert result == []


def test_list_weekly_contracts_ambiguous_expiry_returns_none_not_exception():
    """同一代號對應兩個不同到期日 → 該筆expiry_date回傳None，函式本身
    仍正常回傳、不拋例外，其他正常週選不受影響（spec v5核心修正）。"""
    fake_chain = pd.DataFrame({
        "到期月份(週別)": ["202608F3", "202608F3", "202608F4"],
        "契約到期日": ["20260821", "20260822", "20260828"],  # F3有兩個不同到期日
    })
    result = list_weekly_contracts(fake_chain, date(2026, 8, 19))
    result_dict = dict(result)
    assert result_dict["202608F3"] is None
    assert result_dict["202608F4"] == date(2026, 8, 28)


def test_list_weekly_contracts_ambiguous_sorted_last():
    """expiry_date為None的異常項排在正常項後面。"""
    fake_chain = pd.DataFrame({
        "到期月份(週別)": ["202608F3", "202608F3", "202609W1"],
        "契約到期日": ["20260821", "20260822", "20260902"],
    })
    result = list_weekly_contracts(fake_chain, date(2026, 8, 19))
    assert result[-1][0] == "202608F3"
    assert result[-1][1] is None
