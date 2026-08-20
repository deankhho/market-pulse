"""交易日曆工具：載入人工維護的休市日清單、算交易日差。"""
from datetime import date, timedelta

import yaml


def load_holidays(path: str) -> set[date]:
    """讀 holidays.yaml，回傳 date 集合。YAML 裡每行是 'YYYY-MM-DD   # 註解' 格式，
    PyYAML 會把純日期字串自動解析成 datetime.date，註解會被當成同一個純量值的一部分
    忽略掉——用 safe_load 讀出來是一個 list of date。"""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return set(raw)


def trading_days_until_expiry(data_date: date, expiry_date: date, holidays: set[date]) -> int:
    """區間 (data_date, expiry_date] 內、排除週末與 holidays 後的交易日數。
    data_date == expiry_date（到期日當天）→ 0；expiry_date < data_date（已過期）→ 0。
    對應 spec「到期週判斷」章節的明確演算法定義。"""
    if expiry_date <= data_date:
        return 0
    count = 0
    d = data_date + timedelta(days=1)
    while d <= expiry_date:
        if d.weekday() < 5 and d not in holidays:
            count += 1
        d += timedelta(days=1)
    return count
