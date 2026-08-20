"""Layer 1：選合約。純函式，不碰檔案/網路（spec: Layer 1 定義）。"""
import re
from datetime import date

import pandas as pd

from calendar_utils import trading_days_until_expiry

MONTHLY_SERIES_RE = re.compile(r"^\d{6}$")
EXPIRY_WEEK_THRESHOLD = 3  # trading_days_until_expiry <= 此值就換月


class NoValidContractError(Exception):
    """查無任何純月選候選（regex比對不到），視為輸入資料異常。"""


def select_contract(
    chain_df: pd.DataFrame, data_date: date, holidays: set[date]
) -> tuple[str, date, str]:
    """從完整選擇權鏈選出「近月月選」。

    回傳 (contract_month, expiry_date, selection_reason)。
    查無合法候選拋 NoValidContractError，由呼叫端（Layer 3）當預期內失敗處理，
    不在本層靜默吞掉（spec: Layer 1 篩月選規則）。
    """
    series_col = chain_df["到期月份(週別)"].astype(str)
    is_monthly = series_col.str.match(MONTHLY_SERIES_RE)
    monthly_rows = chain_df[is_monthly]

    if monthly_rows.empty:
        raise NoValidContractError(
            f"查無純月選候選（{data_date} 全部 到期月份(週別) 都不符合 ^\\d{{6}}$）"
        )

    # 契約到期日欄位是 YYYYMMDD 整數/字串，轉成 date 才能跟 data_date 比較與排序
    candidates = (
        monthly_rows[["到期月份(週別)", "契約到期日"]]
        .drop_duplicates()
        .assign(
            expiry_date=lambda df: pd.to_datetime(
                df["契約到期日"].astype(str), format="%Y%m%d"
            ).dt.date
        )
    )
    # 排除已到期契約：契約到期日 >= data_date 才是候選（domain invariant，spec定案 >= 不是 >）
    candidates = candidates[candidates["expiry_date"] >= data_date]
    if candidates.empty:
        raise NoValidContractError(
            f"{data_date} 找不到任何未到期的月選候選（全部契約到期日都早於 data_date）"
        )

    # 用契約到期日數值排序（不是到期月份字串排序，spec明確要求）取最近的
    candidates = candidates.sort_values("expiry_date")

    skipped = []  # 記錄因落入到期週被跳過的候選，讓最終 reason 交代「為什麼不選近月」
    for _, row in candidates.iterrows():
        contract_month = row["到期月份(週別)"]
        expiry_date = row["expiry_date"]
        days_left = trading_days_until_expiry(data_date, expiry_date, holidays)
        if days_left > EXPIRY_WEEK_THRESHOLD:
            if skipped:
                skip_desc = "、".join(
                    f"{m}（距到期 {d} 個交易日，落入到期週 <={EXPIRY_WEEK_THRESHOLD}）"
                    for m, d in skipped
                )
                reason = (
                    f"{skip_desc}被排除，改選近月 {contract_month}，"
                    f"距到期還有 {days_left} 個交易日（>{EXPIRY_WEEK_THRESHOLD}）"
                )
            else:
                reason = (
                    f"近月 {contract_month}，距到期還有 {days_left} 個交易日"
                    f"（>{EXPIRY_WEEK_THRESHOLD}）"
                )
            return (contract_month, expiry_date, reason)
        # 進入到期週，跳過這個候選改看下一個（次近月）
        skipped.append((contract_month, days_left))

    # 所有候選都在到期週內（極端情況：連續多個月選都快到期），退而求其次選最後一個
    last = candidates.iloc[-1]
    return (
        last["到期月份(週別)"],
        last["expiry_date"],
        f"所有候選都在到期週內，退回選最遠到期日的 {last['到期月份(週別)']}",
    )
