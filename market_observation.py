"""Layer 2：算這個合約的OI結構。純函式，不碰檔案/網路，不依賴外部歷史狀態
（spec: v4修正——拿掉「同OI取跟昨日wall較近者」的跨日依賴，改成純函式，
確保同一份輸入資料跑兩次結果完全一樣）。"""
import pandas as pd

SIDE_MAP = {"買權": "call", "賣權": "put"}


def _side_distribution(contract_rows: pd.DataFrame, side_zh: str) -> dict[str, int]:
    """單邊(call或put)的履約價-OI對照表，key字串化整數（spec明確要求，
    避免Python/JS對JSON object key型別認知不一致）。"""
    side_rows = contract_rows[contract_rows["買賣權"] == side_zh]
    dist = {}
    for _, row in side_rows.iterrows():
        strike_key = str(int(float(row["履約價"])))
        oi = int(float(row["未沖銷契約數"]))
        dist[strike_key] = oi
    return dist


def _wall_and_top3(distribution: dict[str, int]) -> tuple[int, list[int]]:
    """同OI值 tie-break：OI值由大到小、同值再依履約價由小到大排序取值——
    純粹基於當天資料本身，不引用外部狀態（spec: Layer 2 tie-break規則）。"""
    items = sorted(distribution.items(), key=lambda kv: (-kv[1], int(kv[0])))
    top3_strikes = [int(k) for k, _ in items[:3]]
    wall = top3_strikes[0] if top3_strikes else None
    return wall, top3_strikes


def compute_observation(chain_df: pd.DataFrame, contract_month: str) -> dict:
    """輸入Layer1選定的contract_month＋完整鏈，輸出這個合約今天的OI結構。
    跟「今天到底有沒有抓到資料」完全無關（spec明確定位）。"""
    contract_rows = chain_df[chain_df["到期月份(週別)"] == contract_month]

    call_dist = _side_distribution(contract_rows, "買權")
    put_dist = _side_distribution(contract_rows, "賣權")

    call_wall, call_top3 = _wall_and_top3(call_dist)
    put_wall, put_top3 = _wall_and_top3(put_dist)

    return {
        "call_wall": call_wall,
        "put_wall": put_wall,
        "call_top3": call_top3,
        "put_top3": put_top3,
        "distribution": {"call": call_dist, "put": put_dist},
    }
