"""Layer 3 輔助：欄位品質驗證。手刻，不引入 pydantic（spec否決項）。"""
import pandas as pd

# 2026-08-19 真實近月(202608)完整鏈是530筆，這個是保守猜測的下限，
# 上線後累積更多天數觀測再校準（比照 fetch_par_value.py 的 ABS_FLOOR 慣例，
# spec明確定義：這是原始資料列數下限，不是別的東西）
ABS_FLOOR = 300

REQUIRED_COLUMNS = {"到期月份(週別)", "契約到期日", "履約價", "買賣權", "未沖銷契約數"}
VALID_SIDES = {"買權", "賣權"}  # 實測真實值是中文，不是英文代碼（Task1驗證過）


def validate_chain(chain_df: pd.DataFrame, abs_floor: int) -> tuple[bool, str | None]:
    """回傳 (是否通過, 失敗原因或None)。任一項不過就回傳 False + 具體原因，
    呼叫端（fetch_oi.py）據此判定 state="error"（spec: 欄位品質驗證章節）。"""
    missing_cols = REQUIRED_COLUMNS - set(chain_df.columns)
    if missing_cols:
        return False, f"缺少必要欄位: {missing_cols}"

    if len(chain_df) < abs_floor:
        return False, f"原始資料列數 {len(chain_df)} 低於下限 {abs_floor}"

    if not chain_df["履約價"].apply(lambda x: pd.notna(x) and float(x) > 0).all():
        return False, "履約價欄位有非正數或無法轉數字的值"

    oi = chain_df["未沖銷契約數"]
    # 未沖銷契約數實際是 float64（Task1實測），驗證「非負且為整數值的浮點數」，
    # 不能檢查 isinstance(x, int)（一定會失敗）
    oi_valid = oi.apply(
        lambda x: pd.notna(x) and float(x) >= 0 and float(x) == int(float(x))
    ).all()
    if not oi_valid:
        return False, "未沖銷契約數欄位有負值或非整數值"

    sides_present = set(chain_df["買賣權"].unique())
    if not VALID_SIDES.issubset(sides_present):
        return False, f"買賣權欄位缺少 call/put 其中一邊，實際值: {sides_present}"

    # 同一(月選序列, 買賣權, 履約價) 不可重複——偵測到重複視為驗證不過，
    # 不做加總/取最後一筆這種隱性決定（spec明確要求）
    dup_key_cols = ["到期月份(週別)", "買賣權", "履約價"]
    if chain_df.duplicated(subset=dup_key_cols).any():
        dup_count = chain_df.duplicated(subset=dup_key_cols).sum()
        return False, f"發現 {dup_count} 筆重複的(合約序列,買賣權,履約價)組合"

    return True, None
