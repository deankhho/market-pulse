from datetime import date
from calendar_utils import load_holidays, trading_days_until_expiry


def test_load_holidays_returns_date_set():
    holidays = load_holidays("data/holidays.yaml")
    assert date(2026, 1, 1) in holidays
    assert isinstance(holidays, set)


def test_trading_days_until_expiry_same_day_is_zero():
    """到期日當天 → 0（spec: data_date == expiry_date 這個邊界案例）"""
    d = date(2026, 8, 19)
    assert trading_days_until_expiry(d, d, set()) == 0


def test_trading_days_until_expiry_already_expired_is_zero():
    """expiry_date < data_date（已過期）→ 0，不應該回傳負數"""
    assert trading_days_until_expiry(date(2026, 8, 20), date(2026, 8, 19), set()) == 0


def test_trading_days_until_expiry_one_trading_day_before():
    """前一個交易日（週二→週三，都不是假日）→ 1"""
    tue = date(2026, 8, 18)  # 週二
    wed = date(2026, 8, 19)  # 週三
    assert trading_days_until_expiry(tue, wed, set()) == 1


def test_trading_days_until_expiry_skips_weekend():
    """週五到下週一，中間跨週末，週末不算交易日"""
    fri = date(2026, 8, 14)   # 週五
    mon = date(2026, 8, 17)   # 下週一
    assert trading_days_until_expiry(fri, mon, set()) == 1  # 只有週一算


def test_trading_days_until_expiry_skips_holiday():
    """區間內有 holidays.yaml 記錄的假日，不算進交易日數"""
    holidays = {date(2026, 4, 3), date(2026, 4, 4)}  # 兒童節+清明連假
    before = date(2026, 4, 2)   # 週四
    after = date(2026, 4, 6)    # 下週一
    # 4/3(五,假日) 4/4(六,假日+週末) 4/5(日,週末) 4/6(一,交易日) → 只有4/6算
    assert trading_days_until_expiry(before, after, holidays) == 1
